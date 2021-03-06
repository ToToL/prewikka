# Copyright (C) 2015-2016 CS-SI. All Rights Reserved.
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

import pkg_resources, sys, os, traceback
from prewikka import log, utils, error, database, env, usergroup, hookmanager
from prewikka.localization import translation

logger = log.getLogger(__name__)


class PluginBase(hookmanager.HookRegistrar):
    plugin_name = None
    plugin_version = None
    plugin_author = None
    plugin_license = None
    plugin_copyright = None
    plugin_description = None

    plugin_database_branch = None
    plugin_database_version = None
    plugin_database_autoupdate = False

    plugin_htdocs = None
    plugin_locale = None

    plugin_deprecate = []
    plugin_mandatory = False


class PluginPreload(PluginBase):
    plugin_classes = []


class PluginManager:
    @staticmethod
    def _handle_attributes(plugin_class, autoupdate):
        if plugin_class.plugin_htdocs:
            env.htdocs_mapping.update(plugin_class.plugin_htdocs)

        if plugin_class.plugin_locale:
            translation.addDomain(*plugin_class.plugin_locale)

        for permission in getattr(plugin_class, "view_permissions", []):
            usergroup.ALL_PERMISSIONS.declare(permission)

        for permission in getattr(plugin_class, "additional_permissions", []):
            usergroup.ALL_PERMISSIONS.declare(permission)

        dh = database.DatabaseUpdateHelper(plugin_class.__module__, plugin_class.plugin_database_version, plugin_class.plugin_database_branch)
        if autoupdate or plugin_class.plugin_database_autoupdate:
            dh.apply()
        else:
            dh.check()

    @staticmethod
    def _handle_section(plugin_class):
        if hasattr(plugin_class, "view_section") and plugin_class.view_section:
            env.menumanager.add_section(plugin_class.view_section)

    def _addPlugin(self, plugin_class, autoupdate, name=None):
        self._handle_attributes(plugin_class, autoupdate)

        self[name or plugin_class.__name__] = plugin_class
        self._count += 1

    def __init__(self, entrypoint, autoupdate=False):
        self._count = 0
        self.__instances = []
        self.__dinstances = {}

        plist = []
        ignore = []

        for i in pkg_resources.iter_entry_points(entrypoint):
            if i.module_name in ignore:
                continue

            logger.debug("loading plugin '%s'" % i.name)
            try:
                plugin_class = i.load()
            except Exception, e:
                logger.exception("%s: %s", i.module_name, e)
                continue

            plist.append((i.module_name, i.name, plugin_class))
            ignore.extend(plugin_class.plugin_deprecate)

        for mname, name, plugin_class in plist:
            if mname in ignore:
                continue

            try:
                if issubclass(plugin_class, PluginPreload):
                    # Get sections from all views before testing plugin database version
                    [self._handle_section(x) for x in plugin_class.plugin_classes]
                    self._handle_attributes(plugin_class, autoupdate)
                    [self._addPlugin(x, autoupdate) for x in plugin_class().plugin_classes]
                else:
                    self._handle_section(plugin_class)
                    self._addPlugin(plugin_class, autoupdate, name=name)

            except error.PrewikkaUserError as e:
                logger.warning("%s: plugin loading failed: %s", plugin_class.__module__, e)
            except Exception as e:
                logger.exception("%s: plugin loading failed: %s", plugin_class.__module__, e)

    def getPluginCount(self):
        return self._count

    def keys(self):
        return self.__dinstances.keys()

    def __iter__(self):
        return iter(self.__instances)

    def __setitem__(self, key, value):
        self.__instances.append(value)
        self.__dinstances[key.lower()] = value

    def __getitem__(self, key):
        return self.__dinstances[key.lower()]

    def __contains__(self, item):
        return item in self.__dinstances

