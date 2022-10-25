""" Metafile Creator.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""

import fnmatch
import hashlib
import logging
import os
import re
import sys
import time

from pathlib import Path
from typing import Dict
from urllib.parse import parse_qs

import bencode

from pyrosimple import error
from pyrosimple.scripts.base import ScriptBase


class MetafileCreator(ScriptBase):
    """
    Create a bittorrent metafile.

    If passed a magnet URL as the only argument, a metafile is created
    in the directory specified via the configuration value 'magnet_watch',
    loadable by rTorrent. Which means you can register 'mktor' as a magnet:
    URL handler in Firefox.
    """

    # argument description for the usage information
    ARGS_HELP = "<dir-or-file> <tracker-url-or-alias>... | <magnet-url>"

    def add_options(self):
        """Add program options."""
        super().add_options()
        # pylint: disable=import-outside-toplevel
        from pyrosimple.util.fmt import bytes_from_human

        self.add_bool_option("-p", "--private", help="disallow DHT and PEX")
        self.add_bool_option("--no-date", help="leave out creation date")
        self.add_value_option(
            "-o",
            "--output-filename",
            "PATH",
            help="optional file name (or target directory) for the metafile",
        )
        self.add_value_option(
            "-r",
            "--root-name",
            "NAME",
            help="optional root name (default is basename of the data path)",
        )
        self.add_value_option(
            "-m",
            "--magnet-watch",
            "NAME",
            help="path to place .meta files from magnet links",
        )
        self.add_value_option(
            "-x",
            "--exclude",
            "PATTERN",
            action="append",
            default=[],
            help="exclude files matching a glob pattern from hashing; can be specified multiple times",
        )
        self.add_value_option(
            "--piece-size",
            "SIZE",
            default="0",
            type=bytes_from_human,
            help="specify the piece size manually: allows byte sizes (e.g. 5M)",
        )
        self.add_value_option(
            "--piece-size-min",
            "SIZE",
            default="32K",
            type=bytes_from_human,
            help="specify a minimum piece size",
        )
        self.add_value_option(
            "--piece-size-max",
            "SIZE",
            default="16M",
            type=bytes_from_human,
            help="specify a maximum piece size",
        )
        self.add_value_option(
            "--comment", "TEXT", help="optional human-readable comment"
        )
        self.add_value_option(
            "-s",
            "--set",
            "KEY=VAL",
            action="append",
            default=[],
            help="set a specific key to the given value; omit the '=' to delete a key; can be specified multiple times",
        )
        self.add_bool_option(
            "-H",
            "--hashed",
            "--fast-resume",
            help="create second metafile containing libtorrent fast-resume information",
        )

    # TODO: Optionally pass torrent directly to rTorrent (--load / --start)
    # TODO: Optionally limit disk I/O bandwidth used (incl. a config default!)
    # TODO: Set "encoding" correctly
    # TODO: Support multi-tracker extension ("announce-list" field)
    # TODO: DHT "nodes" field?! [[str IP, int port], ...]
    # TODO: Web-seeding http://www.getright.com/seedtorrent.html
    #       field 'url-list': ['http://...'] on top-level

    def make_magnet_meta(self, magnet_url):
        """Create a magnet-url torrent."""

        if magnet_url.startswith("magnet:"):
            magnet_url = magnet_url[7:]
        meta = {"magnet-url": "magnet:" + magnet_url}
        magnet_params = parse_qs(magnet_url.lstrip("?"))

        meta_name = magnet_params.get("xt", [hashlib.sha1(magnet_url).hexdigest()])[0]
        if "dn" in magnet_params:
            meta_name = f"{magnet_params['dn'][0]}-{meta_name}"
        meta_name = (
            re.sub(r"[^-_,a-zA-Z0-9]+", ".", meta_name)
            .strip(".")
            .replace("urn.btih.", "")
        )

        if not self.options.magnet_watch:
            self.fatal("You MUST set the '--magnet-watch' config option!")
        meta_path = os.path.join(
            self.options.magnet_watch, f"magnet-{meta_name}.torrent"
        )
        self.LOG.debug("Writing magnet-url metafile %r...", meta_path)

        try:
            bencode.bwrite(meta_path, meta)
        except OSError as exc:
            self.fatal("Error writing magnet-url metafile %r (%s)", (meta_path, exc))
            raise

    def mainloop(self):
        """The main loop."""
        # pylint: disable=import-outside-toplevel
        from pyrosimple import config
        from pyrosimple.util import metafile

        # pylint: enable=import-outside-toplevel

        if len(self.args) == 1 and "=urn:btih:" in self.args[0]:
            # Handle magnet link
            self.make_magnet_meta(self.args[0])
            return

        if not self.args:
            self.parser.print_help()
            self.parser.error("No arguments given, nothing to do!")
            self.parser.exit()
        elif len(self.args) < 2:
            self.parser.error(
                "Expected a path and at least one announce URL, got: %s"
                % (" ".join(self.args),)
            )

        # Validate tracker list
        tracker_urls: Dict[str, str] = {}
        for tracker_url in self.args[1:]:
            found_url = ""
            try:
                tracker_alias, found_urls = config.lookup_announce_url(tracker_url)
                found_url = found_urls[0]
            except KeyError:
                tracker_alias = config.map_announce2alias(tracker_url)
                found_url = tracker_url
            if not found_url:
                raise error.ConfigurationError(
                    f"Announce '{tracker_url}' is not a valid URL or alias"
                )
            tracker_urls[tracker_alias] = found_url

        # Create and configure metafile factory
        datapath = Path(self.args[0])
        metapath = Path(datapath)
        if self.options.output_filename:
            metapath = Path(self.options.output_filename)
            if metapath.is_dir():
                metapath = metapath.joinpath(os.path.basename(datapath))
        if datapath.suffix != ".torrent":
            metapath = datapath.with_suffix(".torrent")

        # Build progress bar
        # pylint: disable=import-outside-toplevel
        from pyrosimple.util.ui import HashProgressBar

        with HashProgressBar() as pb:
            if (
                logging.getLogger().isEnabledFor(logging.WARNING)
                and sys.stdout.isatty()
            ):
                c = pb()

                def pb_tracker(totalhashed, totalsize):
                    c.total = totalsize
                    c.items_completed = totalhashed
                    c.progress_bar.invalidate()

                progress = pb_tracker
            else:
                progress = None
            # Create and metafile with the first announce as a placeholder
            torrent = metafile.Metafile.from_path(
                datapath,
                self.args[1],
                progress=progress,
                root_name=self.options.root_name,
                private=self.options.private,
                created_by="PyroSimple",
                ignore=[
                    re.compile(fnmatch.translate(glob))
                    for glob in self.options.exclude + config.settings.MKTOR_IGNORE
                ],
                piece_size=self.options.piece_size,
                piece_size_min=self.options.piece_size_min,
                piece_size_max=self.options.piece_size_max,
            )
        torrent["created by"] = "PyroSimple"
        if self.options.comment:
            torrent["comment"] = self.options.comment
        if not self.options.no_date:
            torrent["creation date"] = int(time.time())

        # If only one announce, just save to file
        for alias, announce in tracker_urls.items():
            torrent["announce"] = announce
            torrent["info"]["source"] = alias
            torrent["info"]["x_cross_seed"] = hashlib.md5(announce.encode()).hexdigest()
            torrent.assign_fields(self.options.set)
            if len(self.args) == 2:
                save_metapath = metapath
            else:
                save_metapath = Path(f"{alias}_{metapath}")
            self.LOG.info("Writing metafile %s...", save_metapath)
            torrent.save(save_metapath)

            # Create second metafile with fast-resume?
            if self.options.hashed:
                try:
                    torrent.add_fast_resume(datapath)
                except OSError as exc:
                    self.fatal(f"Error making fast-resume data ({exc})")
                    raise

                hashed_path = Path(
                    re.sub(r"\.torrent$", "", str(save_metapath)) + "-resume.torrent"
                )
                self.LOG.info("Writing fast-resume metafile %s...", hashed_path)
                try:
                    torrent.save(hashed_path)
                except OSError as exc:
                    self.fatal(
                        f"Error writing fast-resume metafile {hashed_path!r} ({exc})"
                    )
                    raise


def run():  # pragma: no cover
    """The entry point."""
    ScriptBase.setup()
    MetafileCreator().run()


if __name__ == "__main__":
    run()
