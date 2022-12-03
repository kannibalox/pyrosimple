""" rTorrent Watch Jobs.

    Copyright (c) 2012 The PyroScope Project <pyroscope.project@gmail.com>
"""


import os
import threading
import time

from pathlib import Path
from typing import Dict, Optional, Sequence, cast

import inotify.adapters
import inotify.constants

from pyrosimple import config as configuration
from pyrosimple import error
from pyrosimple.job.base import BaseJob
from pyrosimple.torrent import rtorrent
from pyrosimple.util import metafile, rpc


class TreeWatch(BaseJob):
    """Uses a thread to load torrent files via inotify. The scheduled
    run is used to check for the thread's liveness, and optionally try
    to load any files the watch may have missed"""

    def __init__(self, config: Optional[Dict] = None):
        """Initialize watch job and set default"""
        super().__init__(config or {})
        self.watch_thread: Optional[threading.Thread] = None
        self.mask = inotify.constants.IN_CLOSE_WRITE | inotify.constants.IN_MOVED_TO
        self.config.setdefault("print_to_client", True)
        self.config.setdefault("started", False)
        self.config.setdefault("trace_inotify", False)
        self.config.setdefault("check_unhandled", False)
        self.config.setdefault("remove_unhandled", False)
        self.config.setdefault("remove_already_added", False)
        self.config.setdefault("load_mode", "")
        self.config.setdefault("start_immediately", True)
        self.config["paths"] = {
            Path(p).expanduser().absolute()
            for p in self.config["path"].split(os.pathsep)
        }
        self.custom_cmds = {}
        for key, val in self.config.items():
            if key.startswith("cmd_"):
                self.custom_cmds[key] = val
        if self.config["start_immediately"]:
            self.run()

    def run(self):
        """Start the watcher if it's not running, and load any unhandled files"""
        if self.watch_thread is not None and not self.watch_thread.is_alive():
            self.log.warning("Watcher thread died, restarting")
            self.watch_thread = None
        if self.watch_thread is None:
            self.watch_thread = threading.Thread(
                target=self.watch_trees,
                args=(self.config["paths"],),
                daemon=True,
            )
            self.watch_thread.start()
        if self.config["check_unhandled"]:
            for path in self.config["paths"]:
                for filepath in path.rglob("**/*.torrent"):
                    self.load_metafile(filepath)
                    if (
                        self.config["remove_unhandled"]
                        and filepath.exists()
                        and not self.config["dry_run"]
                    ):
                        filepath.unlink()

    def load_metafile_data(self, metapath: Path) -> Optional[metafile.Metafile]:
        """Check metafile validity and return data if validation succeeds"""
        if metapath.suffix not in {".torrent", ".load", ".start", ".queue"}:
            self.log.debug("Unrecognized extension %s, skipping", metapath.suffix)
            return None
        if not metapath.is_file():
            self.log.debug("Path is not a file: %s", metapath)
            return None
        if metapath.stat().st_size == 0:
            self.log.debug("Skipping 0-byte file %s", metapath)
            return None
        metainfo = metafile.Metafile.from_file(metapath)
        try:
            metainfo.check_meta()
        except ValueError as exc:
            self.log.error("Could not validate torrent file %s: %s", metapath, exc)
            return None
        proxy = self.engine.open()
        try:
            proxy.d.hash(metainfo.info_hash())
            self.log.info(
                "Hash %s already found in client, skipping", metainfo.info_hash()
            )
            if self.config["remove_already_added"]:
                metapath.unlink()
            return None
        except rpc.HashNotFound:
            pass
        return cast(metafile.Metafile, metainfo)

    def build_metafile_variables(
        self, metapath: Path, torrent_data: Optional[metafile.Metafile]
    ) -> Dict:
        """Build a list of varibles to apply to templated commands when loading the metafile"""
        if torrent_data is None:
            torrent_data = self.load_metafile_data(metapath)
            if torrent_data is None:
                return {}

        template_vars = {
            "pathname": str(metapath),
            "info_hash": torrent_data.info_hash(),
            "info_name": torrent_data["info"]["name"],
            "watch_path": self.config["path"],
        }
        if torrent_data.get("announce", ""):
            template_vars["tracker_alias"] = configuration.map_announce2alias(
                torrent_data["announce"]
            )
        main_file = torrent_data["info"]["name"]
        if "files" in torrent_data["info"]:
            main_file = list(
                sorted(
                    (i["length"], i["path"][-1]) for i in torrent_data["info"]["files"]
                )
            )[-1][1]
        template_vars["filetype"] = os.path.splitext(main_file)[1]
        template_vars["commands"] = []
        template_vars["rel_path"] = str(metapath)
        for p in self.config["paths"]:
            if metapath.is_relative_to(p):
                template_vars["rel_path"] = metapath.relative_to(p).parent
                break
        flags = str(metapath).split(os.sep)
        flags.extend(flags[-1].split("."))
        template_vars["flags"] = {i for i in flags if i}
        for key, cmd in sorted(self.custom_cmds.items()):
            try:
                template = rtorrent.env.from_string(cmd)
                for split_cmd in rtorrent.format_item(
                    template, {}, defaults=template_vars
                ).split():
                    template_vars["commands"].append(split_cmd.strip())
            except error.LoggableError as exc:
                self.log.error("While expanding '%s' custom command: %r", key, exc)
        template_vars["watch_path"] = {str(p) for p in self.config["paths"]}

        try:
            import guessit  # pylint: disable=import-outside-toplevel

            template_vars["guessit"] = guessit.guessit(
                torrent_data["info"]["name"], options={"single_value": True}
            )
            media_type = template_vars["guessit"].get("type", "unknown")
            container = template_vars["guessit"].get("container", "unknown")
            template_vars["label"] = f"{media_type}/{container}"
        except ImportError:
            pass
        return template_vars

    def load_metafile(self, metapath: Path):
        """Load file into client, with templating and load commands"""
        # Perform some sanity checks on the file
        # Build templating values
        torrent_data = self.load_metafile_data(metapath)
        if torrent_data is None:
            return
        template_vars = self.build_metafile_variables(metapath, torrent_data)

        proxy = self.engine.open()
        if self.config["load_mode"] in ("start", "started"):
            load_cmd = proxy.load.start_verbose
        else:
            load_cmd = proxy.load.verbose
        if "start" in template_vars["flags"]:
            load_cmd = proxy.load.start_verbose
        elif "load" in template_vars["flags"]:
            load_cmd = proxy.load.verbose
        self.log.debug("Templating values are: %r", template_vars)
        if self.config["dry_run"]:
            self.log.info(
                "Would load %s with commands %r", metapath, template_vars["commands"]
            )
            return

        self.log.info(
            "Loading %s with commands %r", metapath, template_vars["commands"]
        )
        load_cmd(rpc.NOHASH, str(metapath), *tuple(template_vars["commands"]))
        time.sleep(0.05)  # let things settle
        # Announce new item
        if self.config["print_to_client"]:
            try:
                name = proxy.d.name(torrent_data.info_hash())
            except rpc.HashNotFound:
                name = "NOHASH"
            proxy.log(rpc.NOHASH, f"{self.name}: Loaded	{name} '{str(metapath)}'")

    def watch_trees(self, paths: Sequence[os.PathLike]):
        """Thread-able inotify watcher"""
        watcher = inotify.adapters.InotifyTrees(
            [str(p) for p in paths], block_duration_s=5, mask=self.mask
        )
        for event in watcher.event_gen():
            if event is None:
                continue
            try:
                header, _type_names, path, filename = event
                if self.config["trace_inotify"]:
                    self.log.info("%r", event)
                # InotifyTrees subscribes to more events than we care
                # about, so we re-filter here.
                if header.mask & self.mask != 0:
                    continue
                metapath = Path(path, filename)
                self.load_metafile(metapath)
            except Exception as exc:  # pylint: disable=broad-except
                self.log.error("Could not load metafile from event %s: %s", event, exc)


if __name__ == "__main__":
    main()


def main():
    """Show available templating values for a file"""
    # pylint: disable=import-outside-toplevel
    import logging
    import pprint
    import sys

    logger = logging.getLogger(__name__)
    if len(sys.argv) < 2:
        logger.error("File path required")
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.is_file():
        logger.error("File '%s' not found", path)
        sys.exit(1)
    job = TreeWatch({"path": "/tmp", "start_immediately": False})
    logging.getLogger().setLevel(logging.INFO)
    job.log.info("Building template variables for '%s'", path)
    job.log.info(
        "Available variables: %s",
        pprint.pformat(job.build_metafile_variables(path, None)),
    )
