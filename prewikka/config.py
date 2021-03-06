# Copyright (C) 2016 CS-SI. All Rights Reserved.
# Author: Yoann Vandoorselaere <yoannv@gmail.com>
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


import re, os, glob
from prewikka import siteconfig, utils



class ParseError(Exception):
    def __init__(self, filename, lineno, line):
        self._message = _("parse error in \"%(txt)s\" at %(file)s line %(line)d") % {'txt': line.rstrip(), 'file': filename, 'line': lineno}

    def __str__(self):
        return self._message


class ConfigParserOption(str):
    def __new__(cls, *args, **kw):
        return str.__new__(cls, args[1])

    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __repr__(self):
        return "<ConfigParserOption %s%s%s>" % (self.name, "=" if self.value else "", self.value or "")


class ConfigParserSection(object):
    def __init__(self, name):
        object.__setattr__(self, "_instance_name", name)
        object.__setattr__(self, "_od", utils.OrderedDict())

    def __repr__(self):
        return "ConfigParserSection<%s,%s>" % (self._instance_name, self._od.items())

    def __setitem__(self, key, value):
        self._od[key] = value

    def __getitem__(self, key):
        return self._od[key]

    def __setattr__(self, key, value):
        self._od[key] = value

    def __getattr__(self, key):
        return self._od[key]

    def __contains__(self, key):
        return self._od.__contains__(key)

    def __iter__(self):
        return self._od.__iter__()

    def get_instance_name(self):
        return self._instance_name

    def get(self, name, default=None):
        return self._od.get(name, default)

    def keys(self):
        return self._od.keys()

    def items(self):
        return self._od.items()

    def values(self):
        return self._od.values()

    def setdefault(self, key, default):
        return self._od.setdefault(key, default)

    @utils.deprecated
    def getOptions(self):
        return self._od.values()

    @utils.deprecated
    def getOption(self, name):
        return self._od[name]

    @utils.deprecated
    def getOptionValue(self, key, value=None):
        return self._od.get(key, value)


class SectionRoot(list):
    def __contains__(self, key):
        return self and self[0].__contains__(key)

    def __getitem__(self, key):
        if isinstance(key, int):
            return list.__getitem__(self, key)
        else:
            return self[0][key]

    def __getattr__(self, attr):
        return getattr(self[0] if self else ConfigParserSection(""), attr)


class MyConfigParser:
    """
    A config parser class ala ConfigParser.ConfigParser (only read operations
    are (will be) supported).
    ConfigParser.ConfigParser did not feed all our needs:
    - we need the '= value' part of option to be optional
    - we need to support special characters (like ':') in option name (for urls)
    - we need to keep the right order of options in sections (this is done via
      the OrderedDict class that subclass dict)
    """

    EMPTY_LINE_REGEXP = re.compile("^\s*(\#.*)?$")
    SECTION_REGEXP = re.compile("^\s*\[\s*(?P<name>[^\s]+)\s*(?P<instance>.+)?]")
    OPTION_REGEXP = re.compile("^\s*(?P<name>[^:=]+)([:=]\s*(?P<value>.+))?$")

    def __init__(self):
        self._sections = utils.OrderedDict()

    def _create_section(self, name, instance):
        if instance:
            instance = instance.strip()

        if not name in self._sections:
            self._sections[name] = SectionRoot()

        for section in self._sections[name]:
            if section.get_instance_name() == instance:
                return section

        self._sections[name].append(ConfigParserSection(instance))
        return self._sections[name][-1]

    def read(self, filename):
        cursection = None

        for lineno, line in enumerate(open(filename).readlines()):
            result = self.EMPTY_LINE_REGEXP.match(line)
            if result:
                continue

            result = self.SECTION_REGEXP.match(line)
            if result:
                cursection = self._create_section(*result.group("name", "instance"))
                continue

            result = self.OPTION_REGEXP.match(line)
            if not result:
                raise ParseError(file.name, lineno + 1, line)

            name, value = result.group("name").strip(), result.group("value")
            cursection[name] = ConfigParserOption(name, value.strip() if value else None)

    def get(self, name, default):
        return self._sections.get(name, default)

    def __getattr__(self, key):
        return self._sections.get(key, SectionRoot())


class Config(MyConfigParser):
    def __init__(self, filename=None):
        MyConfigParser.__init__(self)

        self.read(filename or siteconfig.conf_dir + "/prewikka.conf")

        for fpattern in self.include.keys():
            if not os.path.isabs(fpattern):
                fpattern = os.path.join(siteconfig.conf_dir, fpattern)

            # Files are loaded in alphabetical order
            for fname in sorted(glob.glob(fpattern)):
                self.read(fname)
