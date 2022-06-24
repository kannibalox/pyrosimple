""" rTorrent Queue Manager.

    Copyright (c) 2012 The PyroScope Project <pyroscope.project@gmail.com>
"""

import time

from pyrosimple import error
from pyrosimple.job.base import MatchableJob
from pyrosimple.util import matching, rpc


# pylint: disable=abstract-method
class QueueManager(MatchableJob):
    """rTorrent queue manager implementation."""

    def __init__(self, config=None):
        """Set up queue manager."""
        self.config = config or {}
        print(self.config)
        super().__init__(config)
        self.proxy = None
        self.last_start = 0

        bool_param = lambda key, default: matching.truth(self.config.get(key, default))
        self.config.setdefault("viewname", "main")
        self.config.setdefault("downloading_min", 0)
        self.config.setdefault("downloading_max", 20)
        self.config.setdefault("max_downloading_traffic", 0)
        self.config["log_to_client"] = bool_param("log_to_client", True)
        self.log.info(
            "Startable matcher is: %s",
            self.config["matcher"],
        )
        self.config["downloading"] = matching.create_matcher(
            self.config.get("downloading", "is_active=1 is_complete=0")
        )
        self.log.info(
            "Downloading matcher is: %s",
            self.config["downloading"],
        )

    def _start(self, items):
        """Start some items if conditions are met."""
        # TODO: Filter by a custom date field, for scheduled downloads starting at a certain time
        # or after a given delay

        # TODO: Don't start anything more if download BW is used >= config threshold in %

        # Check if anything more is ready to start downloading
        startable = [i for i in items if self.matcher.match(i)]
        if not startable:
            self.log.debug(
                "Checked %d item(s), none startable according to %s",
                len(items),
                self.config["matcher"],
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
            self.log.debug(
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
            self.log.debug("%d downloading, down %d", len(downloading), down_traffic)
            if down_traffic > int(self.config["max_downloading_traffic"]):
                self.log.debug("Max download traffic reaching, skipping start")
                return

        # Start eligible items
        for idx, item in enumerate(sorted(startable, key=self.sort_key)):
            # Check if we reached 'start_now' in this run
            if idx >= start_now:
                self.log.debug(
                    "Only starting %d item(s) in this run, %d more could be downloading",
                    start_now,
                    len(startable) - idx,
                )
                break

            # TODO: Prevent start of more torrents that can fit on the drive (taking "off" files into account)
            # (restarts items that were stopped due to the "low_diskspace" schedule, and also avoids triggering it at all)

            # Only check the other conditions when we have `downloading_min` covered
            if len(downloading) < self.config["downloading_min"]:
                self.log.debug(
                    "Catching up from %d to a minimum of %d downloading item(s)",
                    len(downloading),
                    self.config["downloading_min"],
                )
            else:
                # Limit to the given maximum of downloading items
                if len(downloading) >= self.config["downloading_max"]:
                    self.log.debug(
                        "Already downloading %d item(s) out of %d max, %d more could be downloading",
                        len(downloading),
                        self.config["downloading_max"],
                        len(startable) - idx,
                    )
                    break

            # If we made it here, start it!
            self.last_start = now
            downloading.append(item)
            if self.config["dry_run"]:
                self.log.info(
                    "Would start %s '%s'",
                    item.hash,
                    item.name,
                )
            else:
                self.log.info(
                    "Starting %s '%s'",
                    item.hash,
                    item.name,
                )
                item.start()
                if self.config["log_to_client"]:
                    self.engine.open().log(
                        rpc.NOHASH,
                        f"{self.__class__.__name__}: Started '{item.name}' {item.alias}",
                    )

    def run(self):
        """Queue manager job callback."""
        try:
            # Get items from 'main' view
            items = list(self.engine.view(self.config["view"]))

            items.sort(key=self.sort_key)

            # Handle found items
            self._start(items)
        except (error.LoggableError, *rpc.ERRORS) as exc:
            self.log.warning(str(exc))
