# Copyright (C) 2004-2016 CS-SI. All Rights Reserved.
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

import json
import pkg_resources
import time

from prewikka import view, utils, localization, env, mainmenu, hookmanager
from . import templates


class SensorListingParameters(mainmenu.MainMenuParameters):
    def register(self):
        mainmenu.MainMenuParameters.register(self)
        self.optional("filter_path", str)
        self.optional("filter_value", str)
        self.optional("status", list, default=[])


class HeartbeatAnalyzeParameters(view.Parameters):
    def register(self):
        self.mandatory("analyzerid", str)


class SensorMessagesDeleteParameters(SensorListingParameters):
    def register(self):
        SensorListingParameters.register(self)
        self.optional("analyzerid", list, default=[])
        self.optional("alerts", str, default=None)
        self.optional("heartbeats", str, default=None)


class SensorListing(view.View):
    view_name = "Agents"
    view_section = "Agents"
    view_parameters = SensorListingParameters
    view_permissions = [ N_("IDMEF_VIEW") ]
    view_template = templates.SensorListing
    view_order = 0
    plugin_htdocs = (("agents", pkg_resources.resource_filename(__name__, 'htdocs')),)

    def __init__(self):
        view.View.__init__(self)
        self._heartbeat_count = int(env.config.general.get("heartbeat_count", 30))
        self._heartbeat_error_margin = int(env.config.general.get("heartbeat_error_margin", 3))

    def _get_analyzers(self):
        criteria = None
        if "filter_path" in self.parameters:
            criteria = "%s == '%s'" % (self.parameters["filter_path"],
                                       utils.escape_criteria(self.parameters["filter_value"]))

        for (analyzerid,) in env.idmef_db.getValues(["heartbeat.analyzer(-1).analyzerid/group_by"], criteria):
            analyzer, heartbeat = env.idmef_db.getAnalyzer(analyzerid)
            status, status_text = utils.get_analyzer_status_from_latest_heartbeat(
                heartbeat, self._heartbeat_error_margin
            )

            if self.parameters["status"] and status not in self.parameters["status"]:
                continue

            delta = float(heartbeat.get("create_time")) - time.time()

            parameters = {"heartbeat.analyzer(-1).analyzerid": analyzerid}
            heartbeat_listing = utils.create_link(view.getViewPath("HeartbeatListing"), parameters)

            parameters = {"analyzer_object_0": "alert.analyzer.analyzerid",
                          "analyzer_operator_0": "=",
                          "analyzer_value_0": analyzerid}
            alert_listing = utils.create_link(view.getViewPath("AlertListing"), parameters)

            parameters = {"analyzerid": analyzerid}
            heartbeat_analyze = utils.create_link(self.view_path + "/HeartbeatAnalyze", parameters)

            node_name = analyzer["node.name"] or _("Node name n/a")
            osversion = analyzer["osversion"] or _("OS version n/a")
            ostype = analyzer["ostype"] or _("OS type n/a")

            yield {"id": analyzerid,
                   "label": "%s - %s %s" % (node_name, ostype, osversion),
                   "location": analyzer["node.location"] or _("Node location n/a"),
                   "node": node_name,
                   "name": analyzer["name"],
                   "model": analyzer["model"],
                   "class": analyzer["class"],
                   "version": analyzer["version"],
                   "latest_heartbeat": localization.format_timedelta(delta, add_direction=True),
                   "status": status,
                   "status_text": status_text,
                   "links": [
                       {"text": _("Alert listing"), "link": alert_listing},
                       {"text": _("Heartbeat listing"), "link": heartbeat_listing},
                       {"text": _("Heartbeat analysis"), "link": heartbeat_analyze,
                        "class": "widget-link", "title": _("Heartbeat analysis")},
                   ]}

    def render(self):
        analyzer_data = list(self._get_analyzers())
        list(hookmanager.trigger("HOOK_AGENTS_EXTRA_CONTENT", analyzer_data))

        self.dataset["data"] = utils.escape_attribute(json.dumps(analyzer_data))
        self.dataset["extra_columns"] = list(hookmanager.trigger("HOOK_AGENTS_EXTRA_COLUMN"))


class SensorMessagesDelete(SensorListing):
    view_parameters = SensorMessagesDeleteParameters
    view_permissions = [ N_("IDMEF_VIEW"), N_("IDMEF_ALTER") ]

    def render(self):
        for analyzerid in self.parameters["analyzerid"]:
            if self.parameters.has_key("alerts"):
                criteria = "alert.analyzer.analyzerid == '%s'" % utils.escape_criteria(analyzerid)
                env.idmef_db.deleteAlert(env.idmef_db.getAlertIdents(criteria))

            if self.parameters.has_key("heartbeats"):
                criteria = "heartbeat.analyzer(-1).analyzerid == '%s'" % utils.escape_criteria(analyzerid)
                env.idmef_db.deleteHeartbeat(env.idmef_db.getHeartbeatIdents(criteria))

        SensorListing.render(self)


class HeartbeatAnalyze(SensorListing):
    view_parameters = HeartbeatAnalyzeParameters
    view_permissions = [ N_("IDMEF_VIEW") ]
    view_template = templates.HeartbeatAnalyze

    def render(self):
        analyzerid = self.parameters["analyzerid"]

        analyzer, heartbeat = env.idmef_db.getAnalyzer(analyzerid)
        delta = float(heartbeat["create_time"]) - time.time()
        analyzer.last_heartbeat_time = localization.format_timedelta(delta, add_direction=True)

        analyzer.status = None
        analyzer.events = [ ]

        idents = env.idmef_db.getHeartbeatIdents(criteria="heartbeat.analyzer(-1).analyzerid == %s" % analyzerid,
                                                      limit=self._heartbeat_count)
        prev = None
        latest = True
        total_interval = 0

        for idx, ident in enumerate(idents):
            cur = env.idmef_db.getHeartbeat(ident)["heartbeat"]
            cur_status, cur_interval, cur_time = cur.get("additional_data('Analyzer status').data")[0], cur["heartbeat_interval"], cur["create_time"]
            cur_time_str = localization.format_datetime(float(cur_time))

            try:
                prev = env.idmef_db.getHeartbeat(idents[idx + 1])["heartbeat"]
                prev_status, prev_time = prev.get("additional_data('Analyzer status').data")[0], prev["create_time"]
            except:
                break

            if not cur_status or not cur_interval:
                continue

            total_interval += int(cur_interval)

            if latest:
                latest = False
                analyzer.status, analyzer.status_meaning = \
                    utils.get_analyzer_status_from_latest_heartbeat(cur, self._heartbeat_error_margin)
                if analyzer.status == "missing":
                    delta = time.time() - float(cur_time)
                    analyzer.events.append({ "time": cur_time_str, "value": _("Sensor is down since %s") % localization.format_timedelta(delta), "type": "down"})

            event = None
            if cur_status == "starting":
                if prev_status == "exiting":
                    event = { "time": cur_time_str, "value": _("Normal sensor start"), "type": "start" }
                else:
                    event = { "time": cur_time_str, "value": _("Unexpected sensor restart"), "type": "unexpected_restart" }

            elif cur_status == "running":
                delta = abs(int(cur_time) - int(prev_time) - int(cur_interval))
                if delta > self._heartbeat_error_margin:
                    delta = localization.format_timedelta(delta, granularity="second")
                    event = { "time": cur_time_str, "value": _("Unexpected heartbeat interval: %(delta)s") % {'delta': delta}, "type": "abnormal_heartbeat_interval" }


            elif cur_status == "exiting":
                event = { "time": cur_time_str, "value": _("Normal sensor stop"), "type": "normal_stop" }


            if event:
                analyzer.events.append(event)


        if not analyzer.status:
            analyzer.status, analyzer.status_meaning = "unknown", _("Unknown")

        if not analyzer.events:
            delta = localization.format_timedelta(total_interval / self._heartbeat_count)
            analyzer.events.append({ "time": "", "value":
                                     _("No anomaly in the last %(count)d heartbeats (one heartbeat every %(delta)s average)") %
                                       {'count': self._heartbeat_count, 'delta':delta}, "type": "no_anomaly" })

        self.dataset["analyzer"] = analyzer
