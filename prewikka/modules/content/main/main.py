# Copyright (C) 2004 Nicolas Delon <nicolas@prelude-ids.org>
# All Rights Reserved
#
# This file is part of the Prelude program.
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
# You should have received a copy of the GNU General Public License
# along with this program; see the file COPYING.  If not, write to
# the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.


import sys
import os

import time
import copy

from prewikka import User, Filter, ParametersNormalizer, utils


from prewikka.modules.content.main.templates import \
     AlertListing, HeartbeatListing, MessageDetails, MessageListing, \
     MessageSummary, SensorAlertListing, SensorHeartbeatListing, \
     SensorListing, FilterEdition, CommandOutput, HeartbeatAnalyze



class _MyTime:
    def __init__(self, t=None):
        self._t = t or time.time()
        self._index = 5 # second index

    def __getitem__(self, key):
        try:
            self._index = [ "year", "month", "day", "hour", "min", "sec" ].index(key)
        except ValueError:
            raise KeyError(key)
        
        return self

    def round(self, unit):
        t = list(time.localtime(self._t))
        if unit != "sec":
            t[5] = 0
            if unit != "min":
                t[4] = 0
                if unit != "hour":
                    t[3] = 0
                    if unit != "day":
                        t[2] = 1
                        if unit != "month":
                            t[1] = 1
                            t[0] += 1
                        else:
                            t[1] += 1
                    else:
                        t[2] += 1
                else:
                    t[3] += 1
            else:
                t[4] += 1
        else:
            t[5] += 1
        self._t = time.mktime(t)                

    def __add__(self, value):
        t = time.localtime(self._t)
        t = list(t)
        t[self._index] += value
        t = time.mktime(t)
        return _MyTime(t)

    def __sub__(self, value):
        return self + (-value)

    def __str__(self):
        return utils.time_to_ymdhms(time.localtime(self._t))
    
    def __int__(self):
        return int(self._t)



class MessagePM(ParametersNormalizer.ParametersNormalizer):
    def register(self):
        self.mandatory("analyzerid", long)
        self.mandatory("ident", long)



class MessageListingPM(ParametersNormalizer.ParametersNormalizer):
    def register(self):
        self.optional("inline_filter_name", str)
        self.optional("inline_filter_value", str)
        self.optional("filter", str)
        self.optional("timeline_value", int, default=1)
        self.optional("timeline_unit", str, default="hour")
        self.optional("timeline_end", int)
        self.optional("offset", int, default=0)
        self.optional("limit", int, default=50)
        self.optional("timezone", str, "frontend_localtime")

    def normalize(self, parameters):
        ParametersNormalizer.ParametersNormalizer.normalize(self, parameters)

        for p1, p2 in ("inline_filter_name", "inline_filter_value"), ("timeline_value", "timeline_unit"):
            if parameters.has_key(p1) ^ parameters.has_key(p2):
                raise ParametersNormalizer.MissingParameterError(parameters.has_key(p1) and p1 or p2)

        if not parameters["timezone"] in ("frontend_localtime", "sensor_localtime", "utc"):
            raise ParametersNormalizer.InvalidValueError("timezone", parameters["timezone"])
        


class HostCommandPM(ParametersNormalizer.ParametersNormalizer):
    def register(self):
        self.mandatory("host", str)



class DeletePM:
    def register(self):
        self.optional("idents", list, default=[])

    def normalize(self, parameters):
        if not parameters.has_key("idents"):
            return
        
        idents = [ ]
        for ident in parameters["idents"]:
            try:
                analyzerid, message_ident = map(lambda x: long(x), ident.split(":"))
            except ValueError:
                raise ParametersNormalizer.InvalidValueError("idents", parameters["idents"])
            
            idents.append((analyzerid, message_ident))

        parameters["idents"] = idents



class HeartbeatAnalyzePM(ParametersNormalizer.ParametersNormalizer):
    def register(self):
        self.mandatory("analyzerid", long)



class MessageListingDeletePM(MessageListingPM, DeletePM):
    def register(self):
        MessageListingPM.register(self)
        DeletePM.register(self)

    def normalize(self, parameters):
        MessageListingPM.normalize(self, parameters)
        DeletePM.normalize(self, parameters)



class SensorMessageListingPM(MessageListingPM):
    def register(self):
        MessageListingPM.register(self)
        self.mandatory("analyzerid", long)
        


class SensorMessageListingDeletePM(SensorMessageListingPM, DeletePM):
    def register(self):
        SensorMessageListingPM.register(self)
        DeletePM.register(self)

    def normalize(self, parameters):
        SensorMessageListingPM.normalize(self, parameters)
        DeletePM.normalize(self, parameters)



def get_next_filter_element_name(name):
    return chr(ord(name) + 1)


class FilterLoadPM(ParametersNormalizer.ParametersNormalizer):
    def register(self):
        self.mandatory("filter_name", str)



class FilterEditPM(ParametersNormalizer.ParametersNormalizer):
    allow_extra_parameters = True

    def register(self):
        self.optional("filter_name", str)
        self.optional("filter_comment", str)
        self.optional("formula", str)
        
    def normalize(self, parameters):
        ParametersNormalizer.ParametersNormalizer.normalize(self, parameters)
        
        parameters["elements"] = [ ]
        name = "A"
        while True:
            if not parameters.has_key("object_%s" % name):
                break
            parameters["elements"].append((name,
                                           parameters["object_%s" % name],
                                           parameters["operator_%s" % name],
                                           parameters.get("value_%s" % name, "")))
            name = get_next_filter_element_name(name)



class FilterSavePM(FilterEditPM):
    def register(self):
        FilterEditPM.register(self)
        self.mandatory("filter_name", str)



class View:
    def _setView(self, dataset):
        dataset["interface.active_section"] = self.active_section
        dataset["interface.tabs"] = [ (name, utils.create_link(slot)) for name, slot in self.tabs ]
        dataset["interface.active_tab"] = self.active_tab



class EventsView(View):
    active_section = "Events"
    tabs = [("Alerts", "main.alert_listing"),
            ("Heartbeats", "main.heartbeat_listing"),
            ("Filters", "main.alert_filter_edition")]



class AlertsView(EventsView):
    active_tab = "Alerts"



class HeartbeatsView(EventsView):
    active_tab = "Heartbeats"



class AlertFilterEditionView(EventsView):
    active_tab = "Filters"



class SensorsView(View):
    active_section = "Agents"
    tabs = [("Agents", "main.sensor_listing")]
    active_tab = "Agents"



class MessageListingAction:
    def _adjustCriteria(self, request, criteria):
        pass

    def _getInlineFilter(self, wanted):
        for name, object, filter in self.fields:
            if name == wanted:
                return filter

        raise ParametersNormalizer.InvalidParameterError(wanted)

    def _createLink(self, action, parameters, ignore=()):
        return utils.create_link("main.%s" % action,
                                 dict([(k, v) for k, v in parameters.items() if not k in ignore]))

    def _setInlineFilter(self, dataset, parameters):
        dataset["active_inline_filter"] = parameters.get("inline_filter_name", "")
        dataset["remove_active_inline_filter"] = self._createLink(self.listing_action,
                                                                  parameters,
                                                                  [ "inline_filter_name",
                                                                    "inline_filter_value",
                                                                    "offset"])

    def _setTimelineNext(self, dataset, parameters, next):
        dataset["timeline.next"] = self._createLink(self.listing_action,
                                                    dict(parameters.items() + [("timeline_end", int(next))]))

    def _setTimelinePrev(self, dataset, parameters, prev):
        dataset["timeline.prev"] = self._createLink(self.listing_action,
                                                    dict(parameters.items() + [("timeline_end", int(prev))]))

    def _getTimelineRange(self, parameters):
        if parameters.has_key("timeline_end"):
            end = _MyTime(parameters["timeline_end"])
        else:
            end = _MyTime()
            if not parameters["timeline_unit"] in ("min", "hour"):
                end.round(parameters["timeline_unit"])
        
        start = end[parameters["timeline_unit"]] - parameters["timeline_value"]

        return start, end
        
    def _setTimeline(self, dataset, parameters, start, end):
        dataset["timeline.current"] = self._createLink(self.listing_action, parameters, ["timeline_end"])

        dataset["timeline.value"] = parameters["timeline_value"]
        dataset["timeline.%s_selected" % parameters["timeline_unit"]] = "selected"
        dataset["timeline.hidden_parameters"] = { "content": "main.%s" % self.listing_action }
        for name in parameters.keys():
            if not name in ("timeline_value", "timeline_unit", "limit", "filter", "timezone"):
                dataset["timeline.hidden_parameters"][name] = parameters[name]

        if parameters["timezone"] == "utc":
            dataset["timeline.start"] = utils.time_to_ymdhms(time.gmtime(int(start)))
            dataset["timeline.end"] = utils.time_to_ymdhms(time.gmtime(int(end)))
            dataset["timeline.range_timezone"] = "UTC"
        else:
            dataset["timeline.start"] = utils.time_to_ymdhms(time.localtime(int(start)))
            dataset["timeline.end"] = utils.time_to_ymdhms(time.localtime(int(end)))
            dataset["timeline.range_timezone"] = "%+.2d:%.2d" % utils.get_gmt_offset()

        if not parameters.has_key("timeline_end") and parameters["timeline_unit"] in ("min", "hour"):
            tmp = copy.copy(end)
            tmp.round(parameters["timeline_unit"])
            tmp = tmp[parameters["timeline_unit"]] - 1
            self._setTimelineNext(dataset, parameters,
                                  tmp[parameters["timeline_unit"]] + parameters["timeline_value"])
            self._setTimelinePrev(dataset, parameters,
                                  tmp[parameters["timeline_unit"]] - (parameters["timeline_value"] - 1))
        else:
            self._setTimelineNext(dataset, parameters,
                                  end[parameters["timeline_unit"]] + parameters["timeline_value"])
            self._setTimelinePrev(dataset, parameters,
                                  end[parameters["timeline_unit"]] - parameters["timeline_value"])

    def _setNavPrev(self, dataset, parameters, offset):
        if offset:
            dataset["nav.first"] = self._createLink(self.listing_action, parameters)
            offset -= parameters["limit"]
            dataset["nav.prev"] = self._createLink(self.listing_action, dict(parameters.items() + [("offset", offset)]))
        else:
            dataset["nav.prev"] = None
            
    def _setNavNext(self, dataset, parameters, offset, count):
        if count > offset + parameters["limit"]:
            offset = offset + parameters["limit"]
            dataset["nav.next"] = self._createLink(self.listing_action, dict(parameters.items() + [("offset", offset)]))
            offset = count - ((count % parameters["limit"]) or parameters["limit"])
            dataset["nav.last"] = self._createLink(self.listing_action, dict(parameters.items() + [("offset", offset)]))
        else:
            dataset["nav.next"] = None

    def _copyMessageFields(self, dst, src):
        for name, object, filter  in self.fields:
            dst[name] = src[object]

    def _fetchMessages(self, parameters, prelude, criteria):
        messages = [ ]
        
        for analyzerid, ident in self.getMessageIdents(prelude, criteria, parameters["limit"], parameters["offset"]):
            message = { "analyzerid": analyzerid, "ident": ident }
            messages.append(message)
            tmp = self.getMessage(prelude, analyzerid, ident)
            self._copyMessageFields(message, tmp)
            message["time"] = self.getMessageTime(tmp)
        
        messages.sort(lambda x, y: int(y["time"]) - int(x["time"]))

        return messages

    def _createMessageTimeField(self, t, timezone):
        if t:
            if timezone == "utc":
                t = time.gmtime(t)
            elif timezone == "sensor_localtime":
                t = time.gmtime(int(t) + t.gmt_offset)
            else: # timezone == "frontend_localtime"
                t = time.localtime(t)
            
            current = time.localtime()
        
            if t[:3] == current[:3]: # message time is today
                t = utils.time_to_hms(t)
            else:
                t = utils.time_to_ymdhms(t)
        else:
            t = "n/a"

        return { "value": t }

    def _createMessageField(self, parameters, name, value):
        if not value:
            return { "value": "n/a", "inline_filter": None }

        parameters = dict(parameters.items() + [("inline_filter_name", name), ("inline_filter_value", value)])

        return { "value": value, "inline_filter": self._createLink(self.listing_action, parameters) }

    def _createMessageHostField(self, request, name, value):
        field = self._createMessageField(request.parameters, name, value)
        field["host_commands"] = [ ]
        if not value:
            return field

        for command, action in ("whois", self.whois_action), ("traceroute", self.traceroute_action):
            if request.env.host_commands.has_key(command):
                field["host_commands"].append((command.capitalize(),
                                               self._createLink(action, { "host": value })))

        return field
    
    def _createMessageLink(self, message, action):
        return self._createLink(action, { "analyzerid": message["analyzerid"], "ident": message["ident"] })

    def _addMessage(self, request, fields, message):
        fields["summary"] = self._createMessageLink(message, self.summary_action)
        fields["details"] = self._createMessageLink(message, self.details_action)
        fields["ident"] = message["ident"]
        fields["analyzerid"] = message["analyzerid"]
        self._addMessageFields(request, fields, message)

    def _setMessages(self, request, messages):
        dataset = request.dataset
        parameters = request.parameters
        dataset["messages"] = [ ]
        for message in messages:
            fields = { }
            dataset["messages"].append(fields)
            self._addMessage(request, fields, message)

        dataset["delete_form_hiddens"] = { "content": "main.%s" % self.delete_action }
        dataset["delete_form_hiddens"].update(parameters)

    def _setTimezone(self, request):
        for timezone in "utc", "sensor_localtime", "frontend_localtime":
            if timezone == request.parameters["timezone"]:
                request.dataset["timeline.%s_selected" % timezone] = "selected"
            else:
                request.dataset["timeline.%s_selected" % timezone] = ""
        
    def process(self, request):
        dataset = request.dataset

        self._setView(dataset)

        parameters = copy.copy(request.parameters)
        if parameters.has_key("offset"):
            offset = parameters["offset"]
            del parameters["offset"]

        start, end = self._getTimelineRange(parameters)

        criteria = [ ]
        if parameters.has_key("inline_filter_name") and parameters.has_key("inline_filter_value"):
            criteria.append("%s == '%s'" % (self._getInlineFilter(parameters["inline_filter_name"]),
                                            parameters["inline_filter_value"]))
        criteria.append(self.time_criteria_format % (str(start), str(end)))
        self._adjustCriteria(request, criteria)
        criteria = " && ".join(criteria)

        self._setView(dataset)
        self._setInlineFilter(dataset, parameters)
        self._setTimeline(dataset, parameters, start, end)
        self._setNavPrev(dataset, parameters, offset)

        count = self.countMessages(request.env.prelude, criteria)
        messages = self._fetchMessages(request.parameters, request.env.prelude, criteria)

        dataset["nav.from"] = offset + 1
        dataset["nav.to"] = offset + len(messages)
        dataset["limit"] = parameters["limit"]
        dataset["total"] = count

        self._setNavNext(dataset, parameters, offset, count)
        self._setMessages(request, messages)
        self._setTimezone(request)



class AlertListingAction(MessageListingAction, AlertsView):
    listing_action = "alert_listing"
    delete_action = "alert_delete"
    summary_action = "alert_summary"
    details_action = "alert_details"
    whois_action = "alert_whois"
    traceroute_action = "alert_traceroute"
    time_criteria_format = "alert.create_time >= '%s' && alert.create_time < '%s'"
    message_criteria_format = "alert.analyzer.analyzerid == '%d' && alert.messageid == '%d'"
    fields = [ ("severity", "alert.assessment.impact.severity", "alert.assessment.impact.severity"),
               ("completion", "alert.assessment.impact.completion", "alert.assessment.impact.completion"),
               ("classification", "alert.classification.text", "alert.classification.text"),
               ("source", "alert.source(0).node.address(0).address", "alert.source.node.address.address"),
               ("sport", "alert.source(0).service.port", "alert.source.node.service.port"),
               ("suser_name", "alert.source(0).user.user_id(0).name", "alert.source.user.user_id.name"),
               ("suser_uid", "alert.source(0).user.user_id(0).number", "alert.source.user.user_id.number"),
               ("sprocess_name", "alert.source(0).process.name", "alert.source.process.name"),
               ("sprocess_pid", "alert.source(0).process.pid", "alert.source.process.pid"),
               ("target", "alert.target(0).node.address(0).address", "alert.target.node.address.address"),
               ("tport", "alert.target(0).service.port", "alert.target.node.service.port"),
               ("tuser_name", "alert.target(0).user.user_id(0).name", "alert.target.user.user_id.name"),
               ("tuser_uid", "alert.target(0).user.user_id(0).number", "alert.target.user.user_id.number"),
               ("tprocess_name", "alert.target(0).process.name", "alert.target.process.name"),
               ("tprocess_pid", "alert.target(0).process.pid", "alert.target.process.pid"),
               ("sensor", "alert.analyzer.name", "alert.analyzer.name"),
               ("sensor_node_name", "alert.analyzer.node.name", "alert.analyzer.node.name") ]

    def countMessages(self, prelude, criteria):
        return prelude.countAlerts(criteria)

    def getMessageIdents(self, prelude, *args, **kwargs):
        return apply(prelude.getAlertIdents, args, kwargs)

    def getMessage(self, prelude, analyzerid, ident):
        return prelude.getAlert(analyzerid, ident)

    def getMessageTime(self, message):
        return message["alert.create_time"] or 0

    def _copyMessageFields(self, dst, src):
        MessageListingAction._copyMessageFields(self, dst, src)
        
        urls = [ ]
        cnt = 0

        while True:
            origin = src["alert.classification.reference(%d).origin" % cnt]
            if origin is None:
                break
            
            name = src["alert.classification.reference(%d).name" % cnt]
            if not name:
                continue

            url = src["alert.classification.reference(%d).url" % cnt]
            if not url:
                continue
            
            urls.append("<a href='%s'>%s:%s</a>" % (url, origin, name))

            cnt += 1

        if urls:
            dst["classification_references"] = "(" + ", ".join(urls) + ")"
        else:
            dst["classification_references"] = ""
        
    def _addMessageFields(self, request, fields, alert):
        fields["severity"] = { "value": alert["severity"] or "low" }
        fields["completion"] = { "value": alert["completion"] }
        
        for name in ("analyzerid", "ident", "sensor_node_name",
                     "sport", "suser_name", "suser_uid", "sprocess_name", "sprocess_pid",
                     "tport", "tuser_name", "tuser_uid", "tprocess_name", "tprocess_pid"):
            fields[name] = { "value": alert[name] }
        
        for name in "classification", "sensor":
            fields[name] = self._createMessageField(request.parameters, name, alert[name])

        fields["classification_references"] = alert["classification_references"]
        
        for name in  "source", "target",:
            fields[name] = self._createMessageHostField(request, name, alert[name])
        
        fields["time"] = self._createMessageTimeField(alert["time"], request.parameters["timezone"])

    def getFilters(self, storage, login):
        return storage.getAlertFilters(login)

    def getFilter(self, storage, login, name):
        return storage.getAlertFilter(login, name)

    def _adjustCriteria(self, request, criteria):
        if request.parameters.has_key("filter"):
            filter = self.getFilter(request.env.storage, request.user.login, request.parameters["filter"])
            criteria.append("(%s)" % str(filter))

    def process(self, request):
        MessageListingAction.process(self, request)
        request.dataset["filters"] = self.getFilters(request.env.storage, request.user.login)
        request.dataset["current_filter"] = request.parameters.get("filter", "")



class HeartbeatListingAction(MessageListingAction, HeartbeatsView):
    listing_action = "heartbeat_listing"
    delete_action = "heartbeat_delete"
    summary_action = "heartbeat_summary"
    details_action = "heartbeat_details"
    whois_action = "heartbeat_whois"
    traceroute_action = "heartbeat_traceroute"
    time_criteria_format = "heartbeat.create_time >= '%s' && heartbeat.create_time < '%s'"
    message_criteria_format = "heartbeat.analyzer.analyzerid == '%d' && heartbeat.messageid == '%d'"
    fields = [ ("agent", "heartbeat.analyzer.name", "heartbeat.analyzer.name"),
               ("node_address", "heartbeat.analyzer.node.address(0).address", "heartbeat.analyzer.node.address.address"),
               ("node_name", "heartbeat.analyzer.node.name", "heartbeat.analyzer.node.name"),
               ("type", "heartbeat.analyzer.model", "heartbeat.analyzer.model") ]

    def countMessages(self, prelude, criteria):
        return prelude.countHeartbeats(criteria)

    def getMessageIdents(self, prelude, *args, **kwargs):
        return apply(prelude.getHeartbeatIdents, args, kwargs)

    def getMessage(self, prelude, analyzerid, ident):
        return prelude.getHeartbeat(analyzerid, ident)

    def getMessageTime(self, message):
        return message["heartbeat.create_time"]

    def _addMessageFields(self, request, fields, heartbeat):
        for name in "ident", "analyzerid", "agent", "node_name", "type":
            fields[name] = self._createMessageField(request.parameters, name, heartbeat[name])
        fields["node_address"] = self._createMessageHostField(request, "address", heartbeat["node_address"])
        fields["time"] = self._createMessageTimeField(heartbeat["time"], request.parameters["timezone"])



class MessageSummaryAction:
    def beginSection(self, title):
        self._current_section = { }
        self._current_section["title"] = title
        self._current_section["entries"] = [ ]

    def newSectionEntry(self, name, value, emphase=False):
        if value is None or value == "":
            return

        self._current_section["entries"].append({ "name": name, "value": value, "emphase": emphase })

    def endSection(self, dataset):
        if self._current_section["entries"]:
            dataset["sections"].append(self._current_section)

    def buildAnalyzer(self, dataset, alert, root=""):
        if alert[root + "analyzer.analyzerid"] == None:
            return
        
        self.beginSection("Analyzer")
        self.newSectionEntry("Analyzerid", alert[root + "analyzer.analyzerid"])
        self.newSectionEntry("Manufacturer", alert[root + "analyzer.manufacturer"])
        self.newSectionEntry("Model", alert[root + "analyzer.model"], emphase=True)
        self.newSectionEntry("Version", alert[root + "analyzer.version"])
        self.newSectionEntry("Class", alert[root + "analyzer.class"])
        self.newSectionEntry("Operating System", "%s %s" %
                             (alert[root + "analyzer.ostype"], alert[root + "analyzer.osversion"]))
        self.newSectionEntry("Node name", alert[root + "analyzer.node.name"])
        self.newSectionEntry("Address", alert[root + "analyzer.node.address(0).address"])
        self.newSectionEntry("Process", alert[root + "analyzer.process.name"])
        self.newSectionEntry("Pid", alert[root + "analyzer.process.pid"])
        self.endSection(dataset)

        self.buildAnalyzer(dataset, alert, root + "analyzer.")

    def buildAdditionalData(self, dataset, alert):
        self.beginSection("Additional Data")
        
        i= 0
        while True:
            meaning = alert["additional_data(%d).meaning" % i]
            if not meaning:
                break
            value = alert["additional_data(%d).data" % i]
            if alert["additional_data(%d).type" % i] == "byte-string":
                value = utils.hexdump(value)
            emphase = (alert["analyzer.model"] == "Prelude LML" and alert["additional_data(%d).meaning" % i] == "Original Log")
            self.newSectionEntry(meaning, value, emphase)
            i += 1
        
        self.endSection(dataset)
    


class AlertSummaryAction(MessageSummaryAction, AlertsView):
    def buildTime(self, dataset, alert):
        self.beginSection("Dates")
        self.newSectionEntry("Create time", alert["create_time"])
        self.newSectionEntry("Detect time", alert["detect_time"], emphase=True)
        self.newSectionEntry("Analyzer time", alert["analyzer_time"])
        self.endSection(dataset)

    def buildClassification(self, dataset, alert):
        if not alert["classification.text"]:
            return

        self.beginSection("Classification")
        self.newSectionEntry("Text", alert["classification.text"])

        cnt = 0

        while True:
            origin = alert["classification.reference(%d).origin" % cnt]
            if origin == None:
                break

            content = alert["classification.reference(%d).name" % cnt]
            
            meaning = alert["classification.reference(%d).meaning" % cnt]
            if meaning:
                content += " (%s)" % meaning

            url = alert["classification.reference(%d).url" % cnt]
            if url:
                content += " <a href='%s'>%s</a>" % (url, url)

            self.newSectionEntry(origin, content)

            cnt += 1

        self.endSection(dataset)

    def buildImpact(self, dataset, alert):
        self.beginSection("Impact")
        self.newSectionEntry("Description", alert["assessment.impact.description"], emphase=True)
        self.newSectionEntry("Severity", alert["assessment.impact.severity"])
        self.newSectionEntry("Type", alert["assessment.impact.type"])
        self.newSectionEntry("Completion", alert["assessment.impact.completion"])
        self.endSection(dataset)

    def buildDirection(self, dataset, alert, direction):
        address = alert["%s(0).node.address(0).address" % direction]
        if address:
            port = alert["%s(0).service.port" % direction]
            if port:
                address += ":%d" % port
            protocol = alert["%s(0).service.protocol" % direction]
            if protocol:
                address += " (%s)" % protocol
            self.newSectionEntry("Address", address, emphase=True)

        self.newSectionEntry("Interface", alert["%s(0).interface" % direction])
        self.newSectionEntry("User", alert["%s(0).user.user_id(0).name" % direction])
        self.newSectionEntry("Uid", alert["%s(0).user.user_id(0).number" % direction])
        self.newSectionEntry("Process", alert["%s(0).process.name" % direction])

    def buildSource(self, dataset, alert):
        self.beginSection("Source")
        self.buildDirection(dataset, alert, "source")
        self.endSection(dataset)

    def buildTarget(self, dataset, alert):
        self.beginSection("Target")
        self.buildDirection(dataset, alert, "target")
        self.newSectionEntry("File", alert["target(0).file(0).name"])
        self.endSection(dataset)

    def process(self, request):
        alert = request.env.prelude.getAlert(request.parameters["analyzerid"], request.parameters["ident"])
        dataset = request.dataset
        dataset["sections"] = [ ]
        self.buildTime(dataset, alert)
        self.buildClassification(dataset, alert)
        self.buildImpact(dataset, alert)
        self.buildSource(dataset, alert)
        self.buildTarget(dataset, alert)
        self.buildAnalyzer(dataset, alert)
        self.buildAdditionalData(dataset, alert)
        self._setView(dataset)



class HeartbeatSummaryAction(MessageSummaryAction, HeartbeatsView):
    def buildTime(self, dataset, heartbeat):
        self.beginSection("Dates")
        self.newSectionEntry("Create time", heartbeat["create_time"])
        self.newSectionEntry("Analyzer time", heartbeat["analyzer_time"])
        self.endSection(dataset)

    def process(self, request):
        heartbeat = request.env.prelude.getHeartbeat(request.parameters["analyzerid"], request.parameters["ident"])
        dataset = request.dataset
        dataset["sections"] = [ ]
        self.buildAnalyzer(dataset, heartbeat)
        self.buildTime(dataset, heartbeat)
        self.buildAdditionalData(dataset, heartbeat)
        self._setView(dataset)



class _Element:
    id = 1
    is_list = False
    check_field = None
    top_element = False
        
    def _humanizeField(self, field):
        return field.replace("_", " ").capitalize()

    def _renderNormal(self, root, field):
        name = self._humanizeField(field)
        field = "%s.%s" % (root, field)
        value = self._alert[field]
        if value is None:
            return None
        
        value = str(value)
        if value == "":
            value = "n/a"
            
        return { "name": name, "value": value }

    def _renderElement(self, root, field, idx=None):
        element = field()
        element._alert = self._alert
        
        if idx is None:
            name = element.name
        else:
            name = "%s(%d)" % (element.name, idx)
        
        if element.check_field:
            if self._alert["%s.%s.%s" % (root, name, element.check_field)] is None:
                return
        
        humanized = self._humanizeField(element.name)
        id = _Element.id
        _Element.id += 1
        entries = element.render("%s.%s" % (root, name))

        return { "name": humanized, "value": { "name": humanized, "id": id, "hidden": True, "entries": entries } }
    
    def _renderList(self, root, field):
        elements = [ ]
        count = 0
        
        while True:
            element = self._renderElement(root, field, count)
            if not element:
                break
            
            elements.append(element)
            count += 1

        return elements
    
    def render(self, root=None):
        entries = [ ]
        
        for field in self.fields:
            if type(field) is str:
                field = self._renderNormal(root, field)
                if field:
                    entries.append(field)
            else:
                if field.is_list:
                    entries += self._renderList(root, field)
                else:
                    element = self._renderElement(root, field)
                    if element:
                        entries.append(element)

        return entries



class WebService(_Element):
    name = "web_service"
    fields = "url", "cgi", "http_method", "arg("
    check_field = "url"



class SNMPService(_Element):
    name = "snmp_service"
    fields = "oid", "community", "security_name", "context_name", "context_engine_id", "command"
    check_field = "oid"



class Service(_Element):
    name = "service"
    fields = "ident", "ip_version", "name", "port", "iana_protocol_number", "iana_protocol_name", "portlist", \
             "protocol", WebService, SNMPService
    check_field = "ident"


class UserID(_Element):
    name = "user_id"
    fields = "ident", "type", "name", "number"
    check_field = "ident"
    is_list = True



class User_(_Element):
    name = "user"
    fields = "ident", "category", UserID
    check_field = "ident"



class Address(_Element):
    name = "address"
    fields = "ident", "category", "vlan_name", "vlan_num", "address", "netmask"
    is_list = True
    check_field = "ident"



class Node(_Element):
    name = "node"
    fields = "ident", "category", "location", "name", Address
    check_field = "ident"
    


class Process(_Element):
    name = "process"
    fields = "ident", "name", "pid", "path", "arg(", "env("
    check_field = "ident"



class FileAccess(_Element):
    name = "file_access"
    fields = "userid", "permission("
    check_field = "userid"
    is_list = True



class Linkage(_Element):
    name = "linkage"
    fields = "category", "name", "path"
    check_field = "category"
    is_list = True



class Inode(_Element):
    name = "inode"
    fields = "change_time", "number", "major_device", "minor_device", "c_major_device", "c_minor_device"
    check_field = "change_time"



class Checksum(_Element):
    name = "checksum"
    fields = "value", "key", "algorithm"
    check_field = "value"
    is_list = True



class File(_Element):
    name = "file"
    fields = "ident", "category", "fstype", "name", "path", "create_time", "modify_time", \
             "access_time", "data_size", "disk_size", FileAccess, Linkage, Inode, Checksum
    check_field = "ident"
    is_list = True



class Target(_Element):
    name = "target"
    fields = "ident", "decoy", "interface", Node, User_, Process, Service, File
    check_field = "ident"
    is_list = True



class Source(_Element):
    name = "source"
    fields = "ident", "spoofed", "interface", Node, User_, Process, Service
    check_field = "ident"
    is_list = True

    

class Confidence(_Element):
    name = "confidence"
    fields = "rating", "confidence"
    check_field = "confidence"



class Action_(_Element):
    name = "action"
    fields = "category", "description"
    is_list = True
    check_field = "description"



class Impact(_Element):
    name = "impact"
    fields = "severity", "completion", "type", "description"



class Reference(_Element):
    name = "reference"
    fields = "origin", "name", "url", "meaning"
    is_list = True
    check_field = "origin"



class Classification(_Element):
    name = "classification"
    fields = "ident", "text", Reference
    check_field = "ident"



class AdditionalData(_Element):
    name = "additional_data"
    fields = "type", "meaning"
    is_list = True
    check_field = "type"

    def render(self, root):
        entries = _Element.render(self, root)
        value = self._alert["%s.data" % root]
        if self._alert["%s.type" % root] == "byte-string":
            value = utils.hexdump(value)
        entries.append({"name": "Data", "value": value})

        return entries



class Assessment(_Element):
    name = "assessment"
    fields = Impact, Action_, Confidence



class Analyzer(_Element):
    name = "analyzer"
    fields = [ "analyzerid", "manufacturer", "model", "version", "class", "ostype", "osversion", \
               Node, Process ]
    check_field = "analyzerid"

    def __init__(self):
        if not Analyzer in Analyzer.fields:
            Analyzer.fields.append(Analyzer)



class AlertIdent(_Element):
    name = "alertident"
    fields = "alertident", "analyzerid"
    is_list = True
    check_field = "alertident"
    


class ToolAlert(_Element):
    name = "tool_alert"
    fields = "name", "command", AlertIdent
    check_field = "name"



class CorrelationAlert(_Element):
    name = "correlation_alert"
    fields = "name", AlertIdent
    check_field = "name"



class OverflowAlert(_Element):
    name = "overflow_alert"
    fields = "program", "size", "buffer"
    check_field = "program"



class AlertDetailsAction(_Element, AlertsView):
    name = "alert"
    fields = "messageid", Assessment, Analyzer, "create_time", "detect_time", "analyzer_time", \
             Source, Target, Classification, AdditionalData, ToolAlert, CorrelationAlert, \
             OverflowAlert
    top_element = True

    def render(self):
        entries = _Element.render(self, "alert")
        return { "name": "Alert", "id": 0, "hidden": False, "entries": entries }

    def process(self, request):
        self._alert = request.env.prelude.getAlert(request.parameters["analyzerid"],
                                                   request.parameters["ident"])
        request.dataset["node"] = self.render()
        
        self._setView(request.dataset)



class HeartbeatDetailsAction(_Element, HeartbeatsView):
    name = "heartbeat"
    fields = "messageid", Analyzer, "create_time", "analyzer_time", AdditionalData
    top_element = True

    def render(self):
        entries = _Element.render(self, "heartbeat")
        return { "name": "Heartbeat", "id": 0, "hidden": False, "entries": entries }

    def process(self, request):
        self._alert = request.env.prelude.getHeartbeat(request.parameters["analyzerid"],
                                                       request.parameters["ident"])
        request.dataset["node"] = self.render()

        self._setView(request.dataset)



class AlertDeleteAction(AlertListingAction):
    def process(self, request):
        for analyzerid, alert_ident in request.parameters["idents"]:
            request.env.prelude.deleteAlert(analyzerid, alert_ident)

        del request.parameters["idents"]
        
        AlertListingAction.process(self, request)



class HeartbeatDeleteAction(HeartbeatListingAction):
    def process(self, request):
        for analyzerid, heartbeat_ident in request.parameters["idents"]:
            request.env.prelude.deleteHeartbeat(analyzerid, heartbeat_ident)

        del request.parameters["idents"]
        
        HeartbeatListingAction.process(self, request)



class HostCommandAction:
    def process(self, request):
        command = request.env.host_commands[self.command]
        stdin, stdout = os.popen2([ command, request.parameters["host"]])
        output = stdout.read()
        output = output.replace(" ", "&nbsp;").replace("\n", "<br/>\n")
        request.dataset["command_output"] = output
        self._setView(request.dataset)



class AlertWhoisAction(HostCommandAction, AlertsView):
    command = "whois"



class HeartbeatWhoisAction(HostCommandAction, HeartbeatsView):
    command = "whois"



class AlertTracerouteAction(HostCommandAction, AlertsView):
    command = "traceroute"



class HeartbeatTracerouteAction(HostCommandAction, HeartbeatsView):
    command = "traceroute"



class HeartbeatAnalyzeAction(SensorsView):
    def __init__(self, config):
        self._heartbeat_count = config.getOptionValue("heartbeat_count", 30)
        self._heartbeat_error_margin = config.getOptionValue("heartbeat_error_margin", 3)
    
    def process(self, request):
        dataset = request.dataset
        prelude = request.env.prelude
        analyzerid = request.parameters["analyzerid"]
        self._setView(dataset)
        
        analyzer = prelude.getAnalyzer(analyzerid)
        analyzer["last_heartbeat_time"] = str(analyzer["last_heartbeat_time"])
        analyzer["events"] = [ ]
        analyzer["status"] = "abnormal_offline"
        analyzer["status_meaning"] = "abnormal offline"
        
        start = time.time()
        rows = prelude.getValues(selection=["heartbeat.messageid", "heartbeat.create_time/order_desc"],
                                 criteria="heartbeat.analyzer.analyzerid == %d" % analyzerid,
                                 limit=self._heartbeat_count)
        newer = None
        latest = True
        total_interval = 0
        
        for ident, t in rows:
            older = prelude.getHeartbeat(analyzerid, ident)
            older_status = older.getAdditionalData("Analyzer status")
            older_interval = older.getAdditionalData("Analyzer heartbeat interval")
            if not older_status or not older_interval:
                continue
            older_time = t
            total_interval += int(older_interval)

            if latest:
                latest = False
                analyzer["status"], analyzer["status_meaning"] = \
                                    _get_analyzer_status_from_latest_heartbeat(older_status, older_time, older_interval,
                                                                                self._heartbeat_error_margin)
                if analyzer["status"] == "abnormal_offline":
                    analyzer["events"].append({ "value": "sensor is down since %s" % older_time, "type": "down"})
            if newer:
                event = None
                
                if newer_status == "starting":
                    if older_status == "exiting":
                        event = { "value": "normal sensor start at %s" % str(newer_time),
                                  "type": "start" }
                    else:
                        event = { "value": "unexpected sensor restart at %s" % str(newer_time),
                                  "type": "unexpected_restart" }

                if newer_status == "running":
                    if abs(int(newer_time) - int(older_time) - int(older_interval)) > self._heartbeat_error_margin:
                        event = { "value": "abnormal heartbeat interval between %s and %s" %  (older_time, newer_time),
                                  "type": "abnormal_heartbeat_interval" }
                                  

                if newer_status == "exiting":
                    event = { "value": "normal sensor stop at %s" % str(newer_status),
                              "type": "normal_stop" }

                if event:
                    analyzer["events"].append(event)

            newer = older
            newer_status = older_status
            newer_interval = older_interval
            newer_time = older_time

        if not analyzer["events"]:
            analyzer["events"].append({ "value":
                                        "No anomaly in the last %d heartbeats (1 heartbeat every %d s average)" %
                                        (self._heartbeat_count, total_interval / self._heartbeat_count),
                                        "type": "no_anomaly" })

        dataset["analyzer"] = analyzer



class SensorAlertListingAction(SensorsView,
                               AlertListingAction):
    listing_action = "sensor_alert_listing"
    delete_action = "sensor_alert_delete"
    summary_action = "sensor_alert_summary"
    details_action = "sensor_alert_details"

    def _adjustCriteria(self, request, criteria):
        criteria.append("alert.analyzer.analyzerid == %d" % request.parameters["analyzerid"])
        
    def process(self, request):
        AlertListingAction.process(self, request)
        request.dataset["analyzer"] = request.env.prelude.getAnalyzer(request.parameters["analyzerid"])



class SensorAlertDeleteAction(SensorAlertListingAction):
    def process(self, request):
        for analyzerid, alert_ident in request.parameters["idents"]:
            request.env.prelude.deleteAlert(analyzerid, alert_ident)

        del request.parameters["idents"]

        SensorAlertListing.process(self, request)



class SensorHeartbeatListingAction(SensorsView,
                                   HeartbeatListingAction):
    listing_action = "sensor_heartbeat_listing"
    delete_action = "sensor_heartbeat_delete"
    summary_action = "sensor_heartbeat_summary"
    details_action = "sensor_heartbeat_details"
    
    def _adjustCriteria(self, request, criteria):
        criteria.append("heartbeat.analyzer.analyzerid == %d" % request.parameters["analyzerid"])
    
    def process(self, request):
        HeartbeatListingAction.process(self, request)
        request.dataset["analyzer"] = request.env.prelude.getAnalyzer(request.parameters["analyzerid"])



class SensorHeartbeatDeleteAction(SensorHeartbeatListingAction):
    def process(self, request):
        for analyzerid, alert_ident in request.parameters["idents"]:
            request.env.prelude.deleteHeartbeat(analyzerid, alert_ident)

        del request.parameters["idents"]

        SensorHeartbeatListing.process(self, request)



class SensorAlertSummaryAction(SensorsView, AlertSummaryAction):
    pass



class SensorAlertDetailsAction(SensorsView, AlertDetailsAction):
    pass



class SensorHeartbeatSummaryAction(SensorsView, HeartbeatSummaryAction):
    pass



class SensorHeartbeatDetailsAction(SensorsView, HeartbeatDetailsAction):
    pass



def _get_analyzer_status_from_latest_heartbeat(heartbeat_status, heartbeat_time, heartbeat_interval,
                                               error_margin):
    if heartbeat_status == "exiting":
        return "normal_offline", "normal offline"
    if time.time() - int(heartbeat_time) > int(heartbeat_interval) + error_margin:
        return "abnormal_offline", "abnormal offline"
    return "online", "online"

    


class SensorListingAction(SensorsView):
    def process(self, request):
        dataset = request.dataset
        prelude = request.env.prelude

        analyzers = [ ]

        analyzerids = prelude.getAnalyzerids()
        for analyzerid in analyzerids:
            analyzer = prelude.getAnalyzer(analyzerid)
            parameters = dict(request.parameters.items() + [("analyzerid", analyzer["analyzerid"])])
            analyzer["alert_listing"] = utils.create_link("main.sensor_alert_listing", parameters)
            analyzer["heartbeat_listing"] = utils.create_link("main.sensor_heartbeat_listing", parameters)
            analyzer["heartbeat_analyze"] = utils.create_link("main.heartbeat_analyze", parameters)

            analyzer["status"], analyzer["status_meaning"] = \
                                _get_analyzer_status_from_latest_heartbeat(analyzer["last_heartbeat_status"],
                                                                           analyzer["last_heartbeat_time"],
                                                                           analyzer["last_heartbeat_interval"],
                                                                           3)

            analyzer["last_heartbeat_time"] = utils.time_to_ymdhms(time.localtime(analyzer["last_heartbeat_time"])) + \
                                              " %+.2d:%.2d" % utils.get_gmt_offset()
            
            analyzers.append(analyzer)

        dataset["analyzers"] = [ ]
        for analyzer in analyzers:
            if analyzer["status"] == "ok":
                dataset["analyzers"].append(analyzer)
            else:
                dataset["analyzers"].insert(0, analyzer)

        self._setView(dataset)



class AlertFilterEdition(AlertFilterEditionView):
    def _setCommon(self, request):
        self._setView(request.dataset)
        request.dataset["filters"] = request.env.storage.getAlertFilters(request.user.login)
        request.dataset["objects"] = Filter.ALERT_OBJECTS
        request.dataset["operators"] = ("==", "!=", "<", "<=", ">", ">=")
        request.dataset["elements"] = [ ]
        request.dataset["fltr.name"] = ""
        request.dataset["fltr.comment"] = ""
        request.dataset["formula"] = ""
        
    def _element(self, name, obj="", operator="", value=""):
        return {
            "name": name,
            "object": obj,
            "operator": operator,
            "value": value
            }

    def _addEmptyElement(self, elements):
        if elements:
            name = get_next_filter_element_name(elements[-1]["name"])
        else:
            name = "A"

        elements.append(self._element(name))

    def _reloadForm(self, request):
        self._setCommon(request)
        parameters = request.parameters
        dataset = request.dataset
        
        name = "A"
        for name, obj, operator, value in parameters["elements"]:
            dataset["elements"].append(self._element(name, obj, operator, value))
            name = get_next_filter_element_name(name)

        if not dataset["elements"]:
            self._addEmptyElement(dataset["elements"])

        dataset["fltr.name"] = parameters.get("filter_name", "")
        dataset["fltr.comment"] = parameters.get("filter_comment", "")

    def edition(self, request):
        self._setCommon(request)
        self._reloadForm(request)
        
        parameters = request.parameters.keys()
        if "save" in parameters:
            self.save(request)
        elif "new_element" in parameters:
            self.newElement(request)
        
    def newElement(self, request):
        self._addEmptyElement(request.dataset["elements"])

    def load(self, request):
        self._setCommon(request)
        filter = request.env.storage.getAlertFilter(request.user.login, request.parameters["filter_name"])
        dataset = request.dataset
        dataset["fltr.name"] = filter.name
        dataset["fltr.comment"] = filter.comment
        dataset["formula"] = filter.formula
        names = filter.elements.keys()
        names.sort()
        for name in names:
            obj, operator, value = filter.elements[name]
            dataset["elements"].append(self._element(name, obj, operator, value))

    def save(self, request):
        parameters = request.parameters
        elements = { }
        for name, obj, operator, value in parameters["elements"]:
            elements[name] = (obj, operator, value)

        filter = Filter.AlertFilter(parameters["filter_name"], parameters.get("filter_comment", ""),
                                    elements, parameters["formula"])

        request.env.storage.setFilter(request.user.login, filter)
        


def load(env, config):
    return {
        "sections": [("Events", "alert_listing"),
                     ("Agents", "sensor_listing")],

        "default_slot": "alert_listing",

        "slots": { # Alerts section
                   "alert_listing": { "handler": AlertListingAction().process,
                                      "parameters": MessageListingPM(),
                                      "permissions": [ User.PERM_IDMEF_VIEW ],
                                      "template": AlertListing.AlertListing },

                   "alert_summary": { "handler": AlertSummaryAction().process,
                                      "parameters": MessagePM(),
                                      "permissions": [ User.PERM_IDMEF_VIEW ],
                                      "template": MessageSummary.MessageSummary },

                   "alert_details": { "handler": AlertDetailsAction().process,
                                      "parameters": MessagePM(),
                                      "permissions": [ User.PERM_IDMEF_VIEW ],
                                      "template": MessageDetails.MessageDetails },

                   "alert_delete": { "handler": AlertDeleteAction().process,
                                     "parameters": MessageListingDeletePM(),
                                     "permissions": [ User.PERM_IDMEF_VIEW, User.PERM_IDMEF_ALTER ],
                                     "template": AlertListing.AlertListing },

                   "alert_filter_edition": { "handler": AlertFilterEdition().edition,
                                             "parameters": FilterEditPM(),
                                             "permissions": [ User.PERM_IDMEF_VIEW ],
                                             "template": FilterEdition.FilterEdition },


                   "alert_filter_load": { "handler": AlertFilterEdition().load,
                                          "parameters": FilterLoadPM(),
                                          "permissions": [ User.PERM_IDMEF_VIEW ],
                                          "template": FilterEdition.FilterEdition },

                   "alert_whois": { "handler": AlertWhoisAction().process,
                                    "parameters": HostCommandPM(),
                                    "permissions": [ User.PERM_IDMEF_VIEW ],
                                    "template": CommandOutput.CommandOutput },

                   "alert_traceroute": { "handler": AlertTracerouteAction().process,
                                         "parameters": HostCommandPM(),
                                         "permissions": [ User.PERM_IDMEF_VIEW ],
                                         "template": CommandOutput.CommandOutput },

                   "heartbeat_whois": { "handler": HeartbeatWhoisAction().process,
                                        "parameters": HostCommandPM(),
                                        "permissions": [ User.PERM_IDMEF_VIEW ],
                                        "template": CommandOutput.CommandOutput },

                   "heartbeat_traceroute": { "handler": HeartbeatTracerouteAction().process,
                                             "parameters": HostCommandPM(),
                                             "permissions": [ User.PERM_IDMEF_VIEW ],
                                             "template": CommandOutput.CommandOutput },
                   

##                    "alert_filter_new_element": { "handler": AlertFilterEdition().newElement,
##                                                  "parameters": FilterEditPM(),
##                                                  "permissions": [ User.PERM_IDMEF_VIEW ],
##                                                  "template": FilterEdition.FilterEdition },

##                    "alert_filter_save": { "handler": AlertFilterEdition().save,
##                                           "parameters": FilterEditPM(),
##                                           "permissions": [ User.PERM_IDMEF_VIEW ],
##                                           "template": FilterEdition.FilterEdition },
                   
                   # Hearbeats section

                   "heartbeat_analyze": { "handler": HeartbeatAnalyzeAction(config).process,
                                          "parameters": HeartbeatAnalyzePM(),
                                          "permissions": [ User.PERM_IDMEF_VIEW ],
                                          "template": HeartbeatAnalyze.HeartbeatAnalyze },

                   "heartbeat_listing": { "handler": HeartbeatListingAction().process,
                                          "parameters": MessageListingPM(),
                                          "permissions": [ User.PERM_IDMEF_VIEW ],
                                          "template": HeartbeatListing.HeartbeatListing },

                   "heartbeat_summary": { "handler": HeartbeatSummaryAction().process,
                                          "parameters": MessagePM(),
                                          "permissions": [ User.PERM_IDMEF_VIEW ],
                                          "template": MessageSummary.MessageSummary },

                   "heartbeat_details": { "handler": HeartbeatDetailsAction().process,
                                          "parameters": MessagePM(),
                                          "permissions": [ User.PERM_IDMEF_VIEW ],
                                          "template": MessageDetails.MessageDetails },

                   "heartbeat_delete": { "handler": HeartbeatDeleteAction().process,
                                         "parameters": MessageListingDeletePM(),
                                         "permissions": [ User.PERM_IDMEF_VIEW, User.PERM_IDMEF_ALTER ],
                                         "template": HeartbeatListing.HeartbeatListing },

                   # Sensors section

                   "sensor_listing": { "handler": SensorListingAction().process,
                                       "permissions": [ User.PERM_IDMEF_VIEW ],
                                       "template": SensorListing.SensorListing },

                   "sensor_alert_listing": { "handler": SensorAlertListingAction().process,
                                             "parameters": SensorMessageListingPM(),
                                             "permissions": [ User.PERM_IDMEF_VIEW ],
                                             "template": SensorAlertListing.SensorAlertListing },

                   "sensor_alert_summary": { "handler": SensorAlertSummaryAction().process,
                                             "parameters": MessagePM(),
                                             "permissions": [ User.PERM_IDMEF_VIEW ],
                                             "template": MessageSummary.MessageSummary },

                   "sensor_alert_details": { "handler": SensorAlertDetailsAction().process,
                                             "parameters": MessagePM(),
                                             "permissions": [ User.PERM_IDMEF_VIEW ],
                                             "template": MessageDetails.MessageDetails },

                   "sensor_alert_delete": { "handler": SensorAlertDeleteAction().process,
                                            "parameters": SensorMessageListingDeletePM(),
                                            "permissions": [ User.PERM_IDMEF_VIEW, User.PERM_IDMEF_ALTER ],
                                            "template": SensorAlertListing.SensorAlertListing },

                   "sensor_heartbeat_listing": { "handler": SensorHeartbeatListingAction().process,
                                                 "parameters": SensorMessageListingPM(),
                                                 "permissions": [ User.PERM_IDMEF_VIEW ],
                                                 "template": SensorHeartbeatListing.SensorHeartbeatListing },

                   "sensor_heartbeat_summary": { "handler": SensorHeartbeatSummaryAction().process,
                                                 "parameters": MessagePM(),
                                                 "permissions": [ User.PERM_IDMEF_VIEW ],
                                                 "template": MessageSummary.MessageSummary },

                   "sensor_heartbeat_details": { "handler": HeartbeatDetailsAction().process,
                                                 "parameters": MessagePM(),
                                                 "permissions": [ User.PERM_IDMEF_VIEW ],
                                                 "template": MessageDetails.MessageDetails },

                   "sensor_heartbeat_delete": { "handler": HeartbeatDeleteAction().process,
                                                "parameters": SensorMessageListingDeletePM(),
                                                "permissions": [ User.PERM_IDMEF_VIEW, User.PERM_IDMEF_ALTER ],
                                                "template": SensorHeartbeatListing.SensorHeartbeatListing },
                   }
        }
