# -*- coding: utf-8 -*-
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

import concurrent.futures
import shutil
import time

from pyrosimple import config as config_ini
from pyrosimple import error
from pyrosimple.util import fmt, pymagic, rpc, templating
from pyrosimple.util.parts import Bunch
from pyrosimple.torrent import engine, matching, formatting, rtorrent


class EngineStats:
    """rTorrent connection statistics logger."""

    def __init__(self, config=None):
        """Set up statistics logger."""
        self.config = config or Bunch()
        self.LOG = pymagic.get_class_logger(self)
        self.LOG.debug("Statistics logger created with config %r", self.config)

    def run(self):
        """Statistics logger job callback."""
        try:
            proxy = config_ini.engine.open()
            self.LOG.info(
                "Stats for %s - up %s, %s",
                config_ini.engine.engine_id,
                fmt.human_duration(
                    proxy.system.time() - config_ini.engine.startup, 0, 2, True
                ).strip(),
                proxy,
            )
        except (error.LoggableError, rpc.ERRORS) as exc:
            self.LOG.warning(str(exc))


class PathMover:
    """Conditionally move torrent paths.
    Currently it just relies on the current datapath"""

    def __init__(self, config=None):
        """Set up statistics logger."""
        self.config = config or Bunch()
        try:
            self.config.max_workers = int(self.config.max_workers)
        except AttributeError:
            self.config.max_workers = 1
        self.proxy = None
        self.LOG = pymagic.get_class_logger(self)
        self.LOG.debug("Path mover created with config %r", self.config)

    def move(self, i: rtorrent.RtorrentItem, target: str):
        """Safely move a torrent path"""
        i.ignore(1)
        i.stop()
        for _ in range(0, 5):
            if i.is_open:
                time.sleep(0.1)
            else:
                break
        shutil.move(i.datapath(), target)
        self.proxy.d.directory.set(i.hash, target)
        self.proxy.d.start(i.hash)
        i.ignore(0)

    def check_and_move(self, i: rtorrent.RtorrentItem):
        """Conditionally move data"""
        template = templating.preparse(self.config.target)
        target = formatting.format_item(template, i)
        if i.directory == target:
            self.LOG.debug("%s already moved, skipping", i.hash)
            return
        if target:
            if not self.config.dry_run:
                self.LOG.info("Moving path for %s to %s", i.hash, target)
                self.move(i, target)
                i.flush()
            else:
                self.LOG.info("Would move %s to %s", i.hash, target)
        else:
            self.LOG.debug("Empty target for %s", i.hash)

    def run(self):
        """Check if any torrents need to be moved"""
        try:
            self.proxy = config_ini.engine.open()
            matcher = matching.ConditionParser(
                engine.FieldDefinition.lookup, "name"
            ).parse(self.config.matcher)
            view = engine.TorrentView(config_ini.engine, "default")
            view.matcher = matcher
            futures = []
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.config.max_workers
            ) as executor:
                # Submit tasks
                for i in config_ini.engine.items(view, cache=False):
                    if matcher(i):
                        futures.append(executor.submit(self.check_and_move, i))
                # Wait and check for exceptions
                for future in concurrent.futures.as_completed(futures):
                    exc = future.result()
                    if exc is not None:
                        self.LOG.error("Could not move: %s: %s", future, exc)
        except (error.LoggableError, *rpc.ERRORS) as exc:
            self.LOG.warning(str(exc))
