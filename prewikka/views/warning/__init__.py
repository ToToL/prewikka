# Copyright (C) 2015 CS-SI. All Rights Reserved.
# Author: Antoine Luong <antoine.luong@c-s.fr>
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

from . import templates
from prewikka import view, template, version, env

class Warning(view.View):
    plugin_name = "Warning"
    plugin_author = version.__author__
    plugin_license = version.__license__
    plugin_version = version.__version__
    plugin_copyright = version.__copyright__
    plugin_description = _("Prewikka Warning message")

    view_template = templates.warning

    def __init__(self):
        view.View.__init__(self)
        env.hookmgr.register("HOOK_TOPLAYOUT_EXTRA_CONTENT", self._toplayout_extra_content_hook)

    def _toplayout_extra_content_hook(self, request, user, dataset):
        if not request.input_cookie.get("sessionid"):
            dset = template.PrewikkaTemplate(self.view_template)
            dataset["toplayout_extra_content"] += dset.render()