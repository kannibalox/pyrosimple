"""Move torrents to a new path.
Primarily intended for move-on-completion, but is intended to be generic.
"""
import shutil

from pathlib import Path

from pyrosimple.job import base
from pyrosimple.torrent import rtorrent


def move(i: rtorrent.RtorrentItem, target: str):
    """Move a torrent path"""
    i.stop()
    shutil.move(str(i.datapath()), target)
    i._engine.rpc.d.directory.set(i.hash, target)
    i.start()


class PathMover(base.MatchableJob):
    """Conditionally move torrent paths.
    Currently it just relies on the current datapath"""

    def __init__(self, config=None):
        """Set up statistics logger."""
        super().__init__(config)
        if not self.config["target"]:
            raise Exception("'target' not defined!")

    def run_item(self, item: rtorrent.RtorrentItem):
        """Conditionally move data"""
        target = rtorrent.format_item_str(self.config["target"], item)
        if not target:
            self.log.debug("Empty target for %s", item.hash)
            return
        if (Path(item.fetch("directory")) == Path(target)) or (
            item.rpc_call("d.is_multi_file")
            and Path(item.fetch("directory")).parent == Path(target)
        ):
            self.log.debug("%s already moved, skipping", item.hash)
            return
        if self.config["dry_run"]:
            self.log.info(
                "Would move %s from '%s' to '%s'", item.hash, item.datapath(), target
            )
            return
        self.log.info(
            "Moving path for %s from '%s' to '%s'", item.hash, item.datapath(), target
        )
        move(item, target)
        item.flush()
