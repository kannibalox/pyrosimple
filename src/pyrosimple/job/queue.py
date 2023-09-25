""" rTorrent Queue Manager.

    Copyright (c) 2012 The PyroScope Project <pyroscope.project@gmail.com>
"""

import time

from pyrosimple.job.base import MatchableJob
from pyrosimple.util import matching, rpc


class QueueManager(MatchableJob):
    """rTorrent queue manager implementation."""

    def __init__(self, config=None):
        """Set up queue manager."""
        # Allow usage of old field names
        if "startable" in config and "matcher" not in config:
            config["matcher"] = config["startable"]
        if "sort_fields" in config and "sort" not in config:
            config["sort"] = config["sort_fields"]
        config.setdefault(
            "matcher", 'is_complete=no is_ignored=no is_open=no message="" done=0'
        )
        super().__init__(config)
        self.last_start: float = 0
        self.downloading_count: int = 0
        self.allowed_start_count: int = 0

        self.config.setdefault("viewname", "main")
        self.config.setdefault("start_at_once", 1)
        self.config.setdefault("intermission", 120)
        self.config.setdefault("downloading", "is_active=1 is_complete=0")
        self.config.setdefault("downloading_min", 0)
        self.config.setdefault("downloading_max", 20)
        self.config.setdefault("downloading_traffic_max", 0)
        self.config["downloading"] = matching.create_matcher(self.config["downloading"])
        self.config["log_to_client"] = matching.truth(
            self.config.get("log_to_client", True)
        )
        self.log.info(
            "Startable matcher is: %s",
            self.config["matcher"],
        )
        self.log.info(
            "Downloading matcher is: %s",
            self.config["downloading"],
        )

    def run(self):
        # Check intermission delay
        now = time.monotonic()
        delayed = int(self.last_start + self.config["intermission"] - now)
        if delayed > 0:
            self.log.debug(
                "Skipping start due to %ds intermission with %ds left",
                self.config["intermission"],
                delayed,
            )
            return
        downloading = list(self.engine.view("incomplete", self.config["downloading"]))
        self.downloading_count = len(downloading)
        # Check download traffic
        if self.config["downloading_traffic_max"] > 0:
            down_traffic = sum(i.down for i in downloading)
            self.log.debug(
                "%d downloading, download traffic is %d", len(downloading), down_traffic
            )
            if down_traffic > int(self.config["downloading_traffic_max"]):
                self.log.debug(
                    "Skipping start due to max download traffic '%s' reached",
                    self.config["downloading_traffic_max"],
                )
                return
        self.allowed_start_count = max(
            self.config["start_at_once"],
            self.config["downloading_min"] - len(downloading),
        )
        if self.allowed_start_count <= 0:
            self.log.debug("Skipping start due to allowed start count reached")
        if self.downloading_count >= self.config["downloading_max"]:
            self.log.debug(
                "Skipping start due to maximum downloading torrents %d reached",
                self.config["downloading_max"],
            )
        self.log.debug("Starting torrents (capped at %d)", self.allowed_start_count)
        # Run parent method
        super().run()

    def run_item(self, item):
        if self.allowed_start_count <= 0:
            return
        if self.downloading_count >= self.config["downloading_max"]:
            return
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
                    f"{self.__class__.__name__}: Started '{item.name}' [{item.alias}]",
                )
        self.downloading_count += 1
        self.allowed_start_count -= 1
        self.last_start = time.monotonic()
