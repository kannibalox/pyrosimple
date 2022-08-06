"""Move torrents to a new path.
Primarily intended for move-on-completion, but is intended to be generic.
"""
import concurrent.futures
import shutil

from pathlib import Path

import pyrosimple

from pyrosimple import error
from pyrosimple.job import base
from pyrosimple.torrent import formatting, rtorrent
from pyrosimple.util import matching, pymagic, rpc


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

    def run_item(self, i: rtorrent.RtorrentItem):
        """Conditionally move data"""
        target = formatting.format_item_str(self.config["target"], i)
        if not target:
            self.log.debug("Empty target for %s", i.hash)
            return
        if (Path(i.fetch("directory")) == Path(target)) or (
            i.rpc_call("d.is_multi_file")
            and Path(i.fetch("directory")).parent == Path(target)
        ):
            self.log.debug("%s already moved, skipping", i.hash)
            return
        if self.config["dry_run"]:
            self.log.info(
                "Would move %s from '%s' to '%s'", i.hash, i.datapath(), target
            )
            return
        self.log.info(
            "Moving path for %s from '%s' to '%s'", i.hash, i.datapath(), target
        )
        move(i, target)
        i.flush()
