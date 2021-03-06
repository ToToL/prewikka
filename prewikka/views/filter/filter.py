# Copyright (C) 2004-2016 CS-SI. All Rights Reserved.
# Author: Yoann Vandoorselaere <yoannv@gmail.com>
# Author: Nicolas Delon <nicolas.delon@prelude-ids.com>
#
# This file is part of the Prewikka program.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import prelude, re
from prewikka import view, error, usergroup, template, database, utils, version, env, hookmanager
from . import templates


class Filter:
    _typetbl = { "generic": "alert", "alert": "alert", "heartbeat": "heartbeat" }

    def __init__(self, name, ftype, comment, elements, formula):
        self.name = name
        self.type = ftype
        self.comment = comment
        self.elements = elements
        self.formula = formula
        crit = prelude.IDMEFCriteria(str(self))

    def _replace(self, element):
        element = element.group(1)
        if element in ("and", "AND", "&&"):
            return "&&"

        if element in ("or", "OR", "||"):
            return "||"

        if not element in self.elements:
            raise error.PrewikkaUserError(_("Invalid filter element"), _("Invalid filter element '%s' referenced from filter formula") % element)

        prev_val = self.elements[element][2]
        elements = self.elements[element]
        for i in hookmanager.trigger("HOOK_FILTER_CRITERIA_LOAD", elements):
            if i:
                elements = i

        criteria, operator, value = elements
        if value == prev_val:
            value = "'%s'" % utils.escape_criteria(utils.filter_value_adjust(operator, value))

        if self.type:
            criteria = ".".join((self._typetbl[self.type], criteria))

        return "%s %s (%s)" % (criteria, operator, value)

    def __str__(self):
        return "(%s)" % re.sub("(\w+)", self._replace, self.formula)


    def get_criteria_cast(self, wanted_type):
        if self.type != "generic" and self.type != wanted_type:
            return None

        old_type = self.type
        self.type = wanted_type
        fstr = str(self)
        self.type = old_type

        return fstr


class FilterDatabase(database.DatabaseHelper):
    def get_filter_list(self, user, ftype=None, name=None):

        type_str=""
        if ftype:
            type_str = " AND (type = %s OR type = 'generic')" % self.escape(ftype)

        l = map(lambda r: r[0], self.query("SELECT name FROM Prewikka_Filter WHERE userid = %s%s%s" % (self.escape(user.id), type_str, self._chk("name", name))))

        for i in hookmanager.trigger("HOOK_FILTER_LISTING", l):
            if i is not None:
                l = i

            continue

        return l

    @database.use_transaction
    def upsert_filter(self, user, filter):
        rows = self.query("SELECT id FROM Prewikka_Filter WHERE userid = %s AND name = %s", user.id, filter.name)

        values = (user.id, filter.type, filter.name, filter.comment, filter.formula)

        if not rows:
            self.query("INSERT INTO Prewikka_Filter (userid, type, name, comment, formula) VALUES (%s, %s, %s, %s, %s)", *values)
            id = int(self.query("SELECT MAX(id) FROM Prewikka_Filter")[0][0])
        else:
            id = int(rows[0][0])
            self.query("DELETE FROM Prewikka_Filter_Criterion WHERE Prewikka_Filter_Criterion.id = %d" % (id, ))
            self.query("UPDATE Prewikka_Filter SET userid=%s, type=%s, name=%s, comment=%s, formula=%s WHERE id = %d", *(values + (id,)))

        for name, element in filter.elements.items():
            self.query("INSERT INTO Prewikka_Filter_Criterion (id, name, path, operator, value) VALUES (%d, %s, %s, %s, %s)",
                       id, name, *element)

    def get_filter(self, user, name):
        rows = self.query("SELECT id, comment, formula, type FROM Prewikka_Filter WHERE userid = %s AND name = %s",
                          user.id, name)
        if len(rows) == 0:
            return None

        id, comment, formula, ftype = rows[0]
        elements = { }

        rows = self.query("SELECT name, path, operator, value FROM Prewikka_Filter_Criterion WHERE id = %d", int(id))
        for element_name, path, operator, value in rows:
            elements[element_name] = path, operator, value

        return Filter(name, ftype, comment, elements, formula)

    def delete_filter(self, user, name=None):
        qstr = ""
        if name:
            qstr = " AND name = %s" % self.escape(name)

        rows = self.query("SELECT id FROM Prewikka_Filter WHERE userid = %s%s" % (self.escape(user.id), qstr))
        idlist = [ id[0] for id in rows ]

        if rows:
            lst = ", ".join(idlist)
            self.query("DELETE FROM Prewikka_Filter_Criterion WHERE Prewikka_Filter_Criterion.id IN (%s)" % lst)
            self.query("DELETE FROM Prewikka_Filter WHERE id IN (%s)" % lst)

        return idlist


class AlertFilterEditionParameters(view.Parameters):
    allow_extra_parameters = True

    def register(self):
        self.optional("mode", str)
        self.optional("filter_name", str)
        self.optional("filter_comment", str, default="")
        self.optional("filter_formula", str, default="")
        self.optional("load", str)

    def normalize(self, *args, **kwargs):
        view.Parameters.normalize(self, *args, **kwargs)

        self["elements"] = [ ]
        for parameter in self.keys():
            idx = parameter.find("object_")
            if idx == -1:
                continue
            name = parameter.replace("object_", "", 1)
            self["elements"].append((name,
                                     self["object_%s" % name],
                                     self["operator_%s" % name],
                                     self.get("value_%s" % name, "")))



class AlertFilterEdition(view.View):
    plugin_name = "Filters management"
    plugin_author = version.__author__
    plugin_license = version.__license__
    plugin_version = version.__version__
    plugin_copyright = version.__copyright__
    plugin_description = N_("Filters management page")
    plugin_database_branch = version.__branch__
    plugin_database_version = "0"

    view_name = N_("Filters")
    view_parameters = AlertFilterEditionParameters
    view_template = templates.FilterEdition
    view_section = N_("Settings")
    view_order = 1
    view_permissions = [ N_("IDMEF_VIEW") ]

    @hookmanager.register("HOOK_USER_DELETE")
    def _user_delete(self, user):
        for i in self._db.get_filter_list(user):
            self._filter_delete(user, i)

    def _filter_delete(self, user, name):
        idlist = self._db.delete_filter(user, name)
        list(hookmanager.trigger("HOOK_FILTER_DELETE", user, name, idlist[0]))

    @hookmanager.register("HOOK_MAINMENU_PARAMETERS_REGISTER")
    def _filter_parameters_register(self, view):
        view.optional("filter", str, save=True)
        return ["filter"]

    @hookmanager.register("HOOK_IDMEFDATABASE_CRITERIA_PREPARE")
    def _filter_get_criteria(self, criteria, ctype):
        menu = env.request.menu
        if not menu:
            return

        fname = menu.parameters.get("filter")
        if not fname:
            return

        f = self._db.get_filter(env.request.user, fname)
        if not f:
            return

        f = f.get_criteria_cast(ctype)
        if f:
            criteria.append(f)

        return f

    @hookmanager.register("HOOK_MAINMENU_EXTRA_CONTENT")
    def _filter_html_menu(self, ctype):
        if ctype not in ("alert", "heartbeat"):
            return

        tmpl = template.PrewikkaTemplate(templates.menu)
        tmpl["current_filter"] = env.request.parameters.get("filter", "")
        tmpl["filters"] = self._db.get_filter_list(env.request.user, ctype)
        return tmpl.render()

    def __init__(self):
        view.View.__init__(self)
        self._db = FilterDatabase()

    def _flatten(self, rootcl):
        ret = []
        for subcl in rootcl:
            if subcl.getValueType() == prelude.IDMEFValue.TYPE_CLASS:
                ret += self._flatten(subcl)
            else:
                ret.append(subcl.getPath(rootidx=1))
        return ret

    def _set_common(self):
        self.dataset["type"] = self.parameters.get("type", "filter")
        self.dataset["filters"] = self._db.get_filter_list(env.request.user)

        self.dataset["alert_objects"] = self._flatten(prelude.IDMEFClass("alert"))
        self.dataset["generic_objects"] = self._flatten(prelude.IDMEFClass("heartbeat"))

        self.dataset["operators"] = [
            ("=", _("Equal")),
            ("=*", _("Equal (case-insensitive)")),
            ("!=", _("Not equal")),
            ("!=*", _("Not equal (case-insensitive)")),
            ("~", _("Regular expression")),
            ("~*", _("Regular expression (case-insensitive)")),
            ("!~", _("Not regular expression")),
            ("!~*", _("Not regular expression (case-insensitive)")),
            ("<", _("Lesser than")),
            ("<=", _("Lesser or equal")),
            (">", _("Greater than")),
            (">=", _("Greater or equal")),
            ("<>", _("Substring")),
            ("<>*", _("Substring (case-insensitive)")),
            ("!<>", _("Not substring")),
            ("!<>*", _("Not substring (case-insensitive)"))]

        self.dataset["elements"] = [self._element("A")]
        self.dataset["fltr.name"] = ""
        self.dataset["fltr.type"] = ""
        self.dataset["fltr.comment"] = ""
        self.dataset["fltr.formula"] = ""

    def _reload(self):
        self.dataset["elements"] = []

        for name, obj, operator, value in self.parameters.get("elements", [ ]):
            self.dataset["elements"].append(self._element(name, obj, operator, value))

        self.dataset["fltr.type"] = self.parameters.get("filter_type", "")
        self.dataset["fltr.name"] = self.parameters.get("filter_name", "")
        self.dataset["fltr.comment"] = self.parameters.get("filter_comment", "")
        self.dataset["fltr.formula"] = self.parameters["filter_formula"]

    def _element(self, name, obj="", operator="", value=""):
        return {
            "name": name,
            "object": obj,
            "operator": operator,
            "value": value
            }

    def _load(self):
        self._set_common()

        fname = self.parameters.get("filter_name")
        if fname:
            filter = self._db.get_filter(env.request.user, fname)

            self.dataset["fltr.type"] = filter.type
            self.dataset["fltr.name"] = filter.name
            self.dataset["fltr.comment"] = filter.comment
            self.dataset["fltr.formula"] = filter.formula
            self.dataset["elements"] = []

            for name in sorted(filter.elements.keys()):
                obj, operator, value = filter.elements[name]
                self.dataset["elements"].append(self._element(name, obj, operator, value))

    def _delete(self):
        fname = self.parameters.get("filter_name")
        if fname:
            self._filter_delete(env.request.user, fname)

        self._set_common()

    def _save(self):
        elements = { }

        for name, obj, operator, value in self.parameters["elements"]:
            elements[name] = (obj, operator, value)
            if name not in self.parameters["filter_formula"]:
                raise error.PrewikkaUserError(_("Could not save Filter"), _("No valid filter formula provided"))

        fname = self.parameters.get("filter_name")
        if not fname:
            raise error.PrewikkaUserError(_("Could not save Filter"), _("No name for this filter was provided"))

        if not self.parameters["filter_formula"]:
            raise error.PrewikkaUserError(_("Could not save Filter"), _("No valid filter formula provided"))

        if self.parameters.get("load") != fname and self._db.get_filter(env.request.user, fname):
            raise error.PrewikkaUserError(_("Could not save Filter"), _("The filter name is already used by another filter"))

        fltr = Filter(fname,
                      self.parameters["filter_type"],
                      self.parameters.get("filter_comment", ""),
                      elements,
                      self.parameters["filter_formula"])

        self._db.upsert_filter(env.request.user, fltr)

        self._set_common()
        self._reload()


    def render(self):
        if self.parameters.get("mode", _("Load")) == _("Load"):
            self._load()

        elif self.parameters["mode"] == _("Save"):
            self._save()

        elif self.parameters["mode"] == _("Delete"):
            self._delete()
