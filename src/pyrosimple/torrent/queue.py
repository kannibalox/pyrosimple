""" rTorrent Queue Manager.

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
import time

from pyrosimple import error
from pyrosimple.torrent import formatting, rtorrent
from pyrosimple.util import matching, pymagic, rpc


class QueueManager:
    """rTorrent queue manager implementation."""

    def __init__(self, config=None):
        """Set up queue manager."""
        self.config = config or {}
        self.proxy = None
        self.last_start = 0
        self.engine = None
        self.LOG = pymagic.get_class_logger(self)
        if "log_level" in self.config:
            self.LOG.setLevel(config["log_level"])
        self.LOG.debug("Queue manager created with config %r", self.config)

        bool_param = lambda key, default: matching.truth(self.config.get(key, default))
        self.config.setdefault("viewname", "main")
        self.config.setdefault("downloading_min", 0)
        self.config.setdefault("downloading_max", 20)
        self.config.setdefault("max_downloading_traffic", 0)
        self.config["quiet"] = bool_param("quiet", False)
        self.config["startable"] = matching.MatcherBuilder().visit(
            matching.QueryGrammar.parse(
                self.config.get(
                    "startable", "[ is_open=no is_active=no is_complete=no ]"
                )
            )
        )
        self.LOG.info(
            "Startable matcher is: %s",
            self.config["startable"],
        )
        self.config["downloading"] = matching.MatcherBuilder().visit(
            matching.QueryGrammar.parse(
                "is_active=1 is_complete=0"
                + (
                    f" [ {self.config['downloading']} ]"
                    if "downloading" in self.config
                    else ""
                )
            )
        )
        self.LOG.info(
            "Downloading matcher is: [ %s ]",
            self.config["downloading"],
        )
        sort_fields = self.config.get("sort_fields", "prio-,loaded,name").strip()
        self.sort_key = (
            formatting.validate_sort_fields(sort_fields) if sort_fields else None
        )

    def _start(self, items):
        """Start some items if conditions are met."""
        # TODO: Filter by a custom date field, for scheduled downloads starting at a certain time
        # or after a given delay

        # TODO: Don't start anything more if download BW is used >= config threshold in %

        # Check if anything more is ready to start downloading
        startable = [i for i in items if self.config["startable"].match(i)]
        if not startable:
            self.LOG.debug(
                "Checked %d item(s), none startable according to %s",
                len(items),
                self.config["startable"],
            )
            return

        # Check intermission delay
        intermission = self.config.get("intermission", 120)
        now = time.time()
        if now < self.last_start:
            # compensate for summer time and other oddities
            self.last_start = now
        delayed = int(self.last_start + intermission - now)
        if delayed > 0:
            self.LOG.debug(
                "Delaying start of %d item(s),"
                " due to %ds intermission with %ds left",
                len(startable),
                intermission,
                delayed,
            )
            return

        # Stick to "start_at_once" parameter, unless "downloading_min" is violated
        downloading = [i for i in items if self.config["downloading"].match(i)]
        start_now = max(
            self.config.get("start_at_once", 1),
            self.config["downloading_min"] - len(downloading),
        )
        start_now = min(start_now, len(startable))

        if self.config["max_downloading_traffic"] > 0:
            down_traffic = sum(i.down for i in downloading)
            self.LOG.debug("%d downloading, down %d", len(downloading), down_traffic)
            if down_traffic > int(self.config["max_downloading_traffic"]):
                self.LOG.debug("Max download traffic reaching, skipping start")
                return

        # Start eligible items
        for idx, item in enumerate(startable):
            # Check if we reached 'start_now' in this run
            if idx >= start_now:
                self.LOG.debug(
                    "Only starting %d item(s) in this run, %d more could be downloading",
                    start_now,
                    len(startable) - idx,
                )
                break

            # TODO: Prevent start of more torrents that can fit on the drive (taking "off" files into account)
            # (restarts items that were stopped due to the "low_diskspace" schedule, and also avoids triggering it at all)

            # Only check the other conditions when we have `downloading_min` covered
            if len(downloading) < self.config["downloading_min"]:
                self.LOG.debug(
                    "Catching up from %d to a minimum of %d downloading item(s)",
                    len(downloading),
                    self.config["downloading_min"],
                )
            else:
                # Limit to the given maximum of downloading items
                if len(downloading) >= self.config["downloading_max"]:
                    self.LOG.debug(
                        "Already downloading %d item(s) out of %d max, %d more could be downloading",
                        len(downloading),
                        self.config["downloading_max"],
                        len(startable) - idx,
                    )
                    break

            # If we made it here, start it!
            self.last_start = now
            downloading.append(item)
            self.LOG.info(
                "%s '%s' [%s, %s]",
                "WOULD start" if self.config["dry_run"] else "Starting",
                item.name,
                item.alias,
                item.hash,
            )
            if not self.config["dry_run"]:
                item.start()
                if not self.config["quiet"]:
                    self.proxy.log(
                        rpc.NOHASH,
                        "{self.__class__.__name__}: Started '{item.name}' {item.alias}",
                    )

    def run(self):
        """Queue manager job callback."""
        try:
            self.engine = rtorrent.RtorrentEngine()
            self.proxy = self.engine.open()

            # Get items from 'pyrotorque' view
            items = list(self.engine.items(self.config["viewname"]))

            if self.sort_key:
                items.sort(key=self.sort_key)

            # Handle found items
            self._start(items)
            self.LOG.debug("%s - %s", self.engine.engine_id, self.proxy)
        except (error.LoggableError, *rpc.ERRORS) as exc:
            # only debug, let the statistics logger do its job
            self.LOG.debug(str(exc))
