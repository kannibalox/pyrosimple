# -*- coding: utf-8 -*-
# pylint: disable=
""" rTorrent Daemon Jobs.

    Copyright (c) 2012 The PyroScope Project <pyroscope.project@gmail.com>
"""
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from pyrosimple.util.parts import Bunch
from pyrosimple import error
from pyrosimple import config as config_ini
from pyrosimple.util import fmt, xmlrpc, pymagic, stats


class EngineStats(object):
    """rTorrent connection statistics logger."""

    def __init__(self, config=None):
        """Set up statistics logger."""
        self.config = config or Bunch()
        self.LOG = pymagic.get_class_logger(self)
        self.LOG.debug("Statistics logger created with config %r" % self.config)

    def run(self):
        """Statistics logger job callback."""
        try:
            proxy = config_ini.engine.open()
            self.LOG.info(
                "Stats for %s - up %s, %s"
                % (
                    config_ini.engine.engine_id,
                    fmt.human_duration(
                        proxy.system.time() - config_ini.engine.startup, 0, 2, True
                    ).strip(),
                    proxy,
                )
            )
        except (error.LoggableError, xmlrpc.ERRORS) as exc:
            self.LOG.warn(str(exc))


def module_test():
    """Quick test using…

    python -m pyrosimple.torrent.jobs
    """
    import pprint
    from pyrosimple import connect

    try:
        engine = connect()
        print("%s - %s" % (engine.engine_id, engine.open()))

        data, views = _flux_engine_data(engine)
        print("data = ")
        pprint.pprint(data)
        print("views = ")
        pprint.pprint(views)

        print("%s - %s" % (engine.engine_id, engine.open()))
    except (error.LoggableError, xmlrpc.ERRORS) as torrent_exc:
        print("ERROR: %s" % torrent_exc)


if __name__ == "__main__":
    module_test()
