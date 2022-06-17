"""Move torrents to a new path.
Primarily intended for move-on-completion, but is intended to be generic.
"""
import concurrent.futures
import shutil
import time

from pathlib import Path

import pyrosimple

from pyrosimple import error
from pyrosimple.torrent import formatting, rtorrent
from pyrosimple.util import matching, pymagic, rpc


def move(i: rtorrent.RtorrentItem, target: str):
    """Move a torrent path"""
    i.stop()
    for _ in range(0, 5):
        if i.rpc_call("d.is_open", cache=False):
            time.sleep(0.1)
        else:
            break
    shutil.move(i.datapath(), target)
    i._engine.rpc.d.directory.set(i.hash, target)
    i.start()


class PathMover:
    """Conditionally move torrent paths.
    Currently it just relies on the current datapath"""

    def __init__(self, config=None):
        """Set up statistics logger."""
        self.config = config or {}
        self.config.setdefault("max_workers", 1)
        self.config.setdefault("dry_run", False)
        if not self.config["target"]:
            raise Exception("'target' not defined!")
        self.engine = None
        self.LOG = pymagic.get_class_logger(self)
        self.LOG.debug("Path mover created with config %r", self.config)

    def check_and_move(self, i: rtorrent.RtorrentItem):
        """Conditionally move data"""
        target = formatting.format_item_str(self.config["target"], i)
        if not target:
            self.LOG.debug("Empty target for %s", i.hash)
            return
        if (Path(i.fetch("directory")) == Path(target)) or (
            i.rpc_call("d.is_multi_file")
            and Path(i.fetch("directory")).parent == Path(target)
        ):
            self.LOG.debug("%s already moved, skipping", i.hash)
            return
        if self.config["dry_run"]:
            self.LOG.info(
                "Would move %s from '%s' to '%s'", i.hash, i.datapath(), target
            )
            return
        self.LOG.info(
            "Moving path for %s from '%s' to '%s'", i.hash, i.datapath(), target
        )
        move(i, target)
        i.flush()

    def run(self):
        """Check if any torrents need to be moved"""
        try:
            self.engine = pyrosimple.connect()
            matcher = matching.create_matcher(self.config["matcher"])
            futures = []
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.config["max_workers"]
            ) as executor:
                # Submit tasks
                for i in self.engine.view("default", matcher):
                    if matcher.match(i):
                        futures.append(executor.submit(self.check_and_move, i))
                # Wait and check for exceptions
                for future in concurrent.futures.as_completed(futures):
                    exc = future.result()
                    if exc is not None:
                        self.LOG.error("Could not move: %s: %s", future, exc)
        except (error.LoggableError, *rpc.ERRORS) as exc:
            self.LOG.warning(str(exc))
