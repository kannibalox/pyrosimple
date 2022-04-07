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
import hashlib
import os
import shutil
import time
import xmlrpc.client

from pathlib import Path
from time import sleep
from typing import Dict, List

import bencode

from pyrosimple import config as config_ini
from pyrosimple import error
from pyrosimple.torrent import engine, formatting, matching, rtorrent
from pyrosimple.util import fmt, metafile, pymagic, rpc, templating
from pyrosimple.util.parts import Bunch


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


def nodes_by_hash_weight(meta_id: str, nodes: List[str]) -> Dict[str, int]:
    """Weight nodes by hashing the meta_id"""
    result = {
        n: int.from_bytes(hashlib.sha256(meta_id.encode() + n.encode()).digest(), "big")
        for n in nodes
    }
    return dict(sorted(result.items(), key=lambda item: item[1]))


def get_custom_fields(infohash, proxy):
    """Try using rtorrent-ps commands to list custom keys, otherwise fall back to reading from a session file."""
    if "d.custom.keys" in proxy.system.listMethods():
        custom_fields = {}
        for key in proxy.d.custom.keys(infohash):
            custom_fields[key] = proxy.d.custom(infohash, key)
    else:
        info_file = Path(proxy.session.path(), "{}.torrent.rtorrent".format(infohash))
        proxy.d.save_full_session(infohash)
        with open(info_file, "rb") as fh:
            custom_fields = bencode.bread(fh)["custom"]
    return custom_fields


class Mover:
    """Move torrent to remote host(s)"""

    def move(
        self,
        infohash,
        remote_proxy,
        fast_resume=True,
        extra_cmds=None,
        keep_basedir=True,
        copy=False,
    ):
        """Moves a torrent to a specific host"""
        if extra_cmds is None:
            extra_cmds = []
        self.LOG.debug(
            "Attempting to %s %s",
            "copy" if copy else "move",
            infohash,
        )
        try:
            remote_proxy.d.hash(infohash)
        except rpc.HashNotFound:
            pass
        else:
            self.LOG.warning("Hash exists remotely")
            return False

        torrent = bencode.bread(
            os.path.join(self.proxy.session.path(), "{}.torrent".format(infohash))
        )

        if keep_basedir:
            esc_basedir = self.proxy.d.directory_base(infohash).replace('"', '"')
            extra_cmds.insert(0, 'd.directory_base.set="{}"'.format(esc_basedir))

        if self.proxy.d.complete(infohash) == 1 and fast_resume:
            self.LOG.debug(
                "Setting fast resume data from %s",
                self.proxy.d.directory_base(infohash),
            )
            metafile.add_fast_resume(torrent, self.proxy.d.directory_base(infohash))

        xml_metafile = xmlrpc.client.Binary(bencode.bencode(torrent))

        if not copy:
            self.proxy.d.stop(infohash)
        self.LOG.debug("Running extra commands on load: {}".format(extra_cmds))
        remote_proxy.load.raw("", xml_metafile, *extra_cmds)
        for _ in range(0, 5):
            try:
                remote_proxy.d.hash(infohash)
            except rpc.HashNotFound:
                sleep(1)
        # After 10 seconds, let the exception happen
        remote_proxy.d.hash(infohash)

        # Keep custom values
        for k, v in get_custom_fields(infohash, self.proxy).items():
            remote_proxy.d.custom.set(infohash, k, v)
        for key in range(1, 5):
            value = getattr(self.proxy.d, "custom{}".format(key))(infohash)
            getattr(remote_proxy.d, "custom{}.set".format(key))(infohash, value)

        if fast_resume:
            remote_proxy.d.start(infohash)
        if not copy:
            self.proxy.d.erase(infohash)
        return True

    def __init__(self, config=None):
        """Initalize torrent mover job"""
        self.config = config or Bunch()
        self.LOG = pymagic.get_class_logger(self)
        self.LOG.debug("Statistics logger created with config %r", self.config)
        self.proxy = None

    def run(self):
        """Statistics logger job callback."""
        try:
            self.proxy = config_ini.engine.open()
            matcher = matching.ConditionParser(
                engine.FieldDefinition.lookup, "name"
            ).parse(f"{self.config.matcher}")
            view = engine.TorrentView(config_ini.engine, "default")
            view.matcher = matcher
            hosts = self.config.hosts.split(",")
            for i in config_ini.engine.items(view, cache=False):
                for host in nodes_by_hash_weight(i.hash + i.alias, hosts):
                    rproxy = rpc.RTorrentProxy(host)
                    metahash = i.hash
                    if self.move(metahash, rproxy):
                        self.LOG.info(
                            "Archived {} to {}".format(
                                metahash, rproxy.system.hostname()
                            )
                        )
                        break
        except (error.LoggableError, *rpc.ERRORS) as exc:
            self.LOG.warning(str(exc))
