#!/usr/bin/env python3
"""Print statistics about downloading items"""
import os

import pyrosimple

from pyrosimple.scripts import base
from pyrosimple.util import fmt


def fmt_duration(secs):
    """Format a duration in seconds."""
    return " ".join(
        fmt.human_duration(secs, 0, precision=2, short=True).strip().split()
    )


def disk_free(path):
    """Return free bytes on partition holding `path`."""
    stats = os.statvfs(path)
    return stats.f_bavail * stats.f_frsize


class DownloadStats(base.ScriptBaseWithConfig):
    """
    Show stats about currently active & pending downloads.
    """

    # argument description for the usage information
    ARGS_HELP = ""

    # set your own version
    VERSION = "1.0"

    FIELDS = ("is_active", "left_bytes", "size_bytes", "down.rate", "priority")
    MIN_STALLED_RATE = 5 * 1024
    STALLED_PERCENT = 10

    def mainloop(self):
        engine = pyrosimple.connect()
        proxy = engine.open()
        all_items = engine.multicall("incomplete", self.FIELDS)

        pending = [d for d in all_items if not d.is_active and d.priority > 0]
        print(
            "Queued items:          ",
            fmt.human_size(sum(d.size_bytes for d in pending)),
            "in",
            len(pending),
            "item(s)",
            "[{} free]".format(
                fmt.human_size(disk_free(proxy.directory.default())).strip()
            ),
        )

        items = [d for d in all_items if d.is_active]
        if not items:
            print("No active downloads!")
            return

        good_rates = [d.down_rate for d in items if d.down_rate > self.MIN_STALLED_RATE]
        stalled_rate = max(
            self.MIN_STALLED_RATE,
            self.STALLED_PERCENT / 100 * sum(good_rates) / len(good_rates)
            if good_rates
            else 0,
        )
        stalled_count = sum(d.down_rate < stalled_rate for d in items)
        global_down_rate = proxy.throttle.global_down.rate()

        total_size = sum(d.size_bytes for d in items)
        total_left = sum(d.left_bytes for d in items)
        eta_list = [0]
        if stalled_count < len(items):
            eta_list = [
                d.left_bytes / d.down_rate for d in items if d.down_rate >= stalled_rate
            ]
        eta_max = total_left / (global_down_rate or 1)

        stalled_info = (
            ", {} stalled below {}/s".format(
                stalled_count, fmt.human_size(stalled_rate).strip()
            )
            if stalled_count
            else ""
        )
        print(
            "Size left to download: ",
            fmt.human_size(total_left),
            "of",
            fmt.human_size(total_size).strip(),
        )
        print("Overall download speed:", fmt.human_size(global_down_rate) + "/s")
        print(
            "ETA (min → max):       ",
            fmt_duration(min(eta_list)),
            "→",
            fmt_duration(eta_max),
            "…",
            fmt_duration(max(eta_list)),
            "[{} item(s){}]".format(len(items), stalled_info),
        )


if __name__ == "__main__":
    DownloadStats().run()
