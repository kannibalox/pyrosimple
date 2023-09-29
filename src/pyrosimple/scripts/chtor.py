""" Metafile Editor.

    Copyright (c) 2010 The PyroScope Project <pyroscope.project@gmail.com>
"""


import copy
import difflib
import hashlib
import logging
import os
import re
import sys
import time
import urllib.parse

from pathlib import Path
from typing import List, Optional, cast

import bencode  # typing: ignore

from pyrosimple import config, error
from pyrosimple.scripts.base import ScriptBase
from pyrosimple.util import metafile


def replace_fields(meta, patterns):
    """Replace patterns in fields."""
    for pattern in patterns:
        try:
            field, regex, subst, _ = pattern.split(pattern[-1])

            # TODO: Allow numerical indices, and "+" for append
            namespace = meta
            keypath = [
                i.replace("\0", ".") for i in field.replace("..", "\0").split(".")
            ]
            for key in keypath[:-1]:
                namespace = namespace[key]

            namespace[keypath[-1]] = re.sub(regex, subst, namespace[keypath[-1]])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise error.UserError(f"Bad substitution '{pattern}' ({exc})!")

    return meta


def diff_metafiles(
    meta1: metafile.Metafile,
    meta2: metafile.Metafile,
    meta1_name="old",
    meta2_name="new",
) -> List[str]:
    """Return a git-style diff between two metafiles"""

    from pyrosimple.util.fmt import (  # pylint: disable=import-outside-toplevel
        BencodeJSONEncoder,
    )

    def encode_meta(meta: metafile.Metafile) -> List[str]:
        """Sanitize and modify meta for better diffing"""
        meta_dict = meta.dict_copy()
        if "info" in meta_dict and "pieces" in meta_dict["info"]:
            meta_dict["info"][
                "pieces"
            ] = f'{len(meta_dict["info"]["pieces"])//20} pieces, md5 hash {hashlib.md5(meta_dict["info"]["pieces"]).hexdigest()}'

        return [
            l + "\n" for l in BencodeJSONEncoder(indent=2).encode(meta_dict).split("\n")
        ]

    meta1_out = encode_meta(meta1)
    meta2_out = encode_meta(meta2)
    return list(difflib.unified_diff(meta1_out, meta2_out, meta1_name, meta2_name))


class MetafileChanger(ScriptBase):
    """Change attributes of a bittorrent metafile."""

    # Keys of rTorrent session data
    RT_RESUME_KEYS = ("libtorrent_resume", "log_callback", "err_callback", "rtorrent")

    def add_options(self):
        """Add program options."""
        super().add_options()

        self.parser.add_argument("metafile", nargs="+", help="Torrent files to modify")
        self.add_bool_option(
            "-n",
            "--dry-run",
            help="don't write changes to disk, just tell what would happen",
        )
        self.add_bool_option(
            "--diff",
            help="display a diff for each change being made",
        )
        self.add_bool_option(
            "-V",
            "--no-validation",
            "--no-skip",
            help="do not validate metafiles before and after change",
        )
        self.add_value_option(
            "-o",
            "--output-directory",
            "PATH",
            help="optional output directory for the modified metafile(s)",
        )
        self.add_bool_option(
            "-p", "--make-private", help="make torrent private (DHT/PEX disabled)"
        )
        self.add_bool_option(
            "-P", "--make-public", help="make torrent public (DHT/PEX enabled)"
        )
        self.add_value_option(
            "-s",
            "--set",
            "KEY=VAL",
            action="append",
            default=[],
            help="set a specific key to the given value; omit the '=' to delete a key",
        )
        self.add_value_option(
            "-r",
            "--regex",
            "KEY/REGEX/SUBST/",
            action="append",
            default=[],
            help="replace pattern in a specific key by the given substitution",
        )
        self.add_bool_option(
            "-C",
            "--clean",
            help="remove all non-standard data from metafile outside the info dict",
        )
        self.add_bool_option(
            "-A",
            "--clean-all",
            help="remove all non-standard data from metafile including inside the info dict",
        )
        self.add_bool_option(
            "-X",
            "--clean-xseed",
            help="like --clean-all, but keep libtorrent resume information",
        )
        self.add_bool_option(
            "-R",
            "--clean-rtorrent",
            help="remove all rTorrent session data from metafile",
        )
        self.add_value_option(
            "-H",
            "--hashed",
            "--fast-resume",
            "DATAPATH",
            help="add libtorrent fast-resume information (use {} in place of the torrent's name in DATAPATH)",
        )
        self.add_value_option(
            "-c",
            "--check-data",
            "PATH",
            help="check the hash against the data in the given path before making any changes",
        )
        self.add_value_option(
            "-T",
            "--tracker",
            "DOMAIN",
            help="filter given torrents for a tracker domain",
        )
        self.add_value_option(
            "-a",
            "--reannounce",
            "URL",
            help="set a new announce URL, but only if the old announce URL matches the new one",
        )
        self.add_value_option(
            "--reannounce-all",
            "URL",
            help="set a new announce URL on ALL given metafiles",
        )
        self.add_bool_option(
            "--no-cross-seed",
            help="when using --reannounce-all, do not add a non-standard field to the info dict ensuring unique info hashes",
        )
        self.add_value_option(
            "--comment", "TEXT", help="set a new comment (an empty value deletes it)"
        )
        self.add_bool_option("--bump-date", help="set the creation date to right now")
        self.add_bool_option("--no-date", help="remove the 'creation date' field")

    def mainloop(self) -> None:
        """The main loop."""
        self.args = self.options.metafile
        if not self.args:
            self.parser.print_help()
            self.parser.error("No metafiles given, nothing to do!")
            self.parser.exit()

        if self.options.reannounce and self.options.reannounce_all:
            self.parser.error("Conflicting options --reannounce and --reannounce-all!")

        # Set filter criteria for metafiles
        filter_url_prefix: Optional[str] = None
        if self.options.reannounce:
            filter_url_prefix = config.map_announce2alias(self.options.reannounce)
            self.log.info(
                "Filtering for metafiles with announce URL %r...",
                filter_url_prefix,
            )
        elif self.options.tracker:
            filter_url_prefix = config.map_announce2alias(self.options.tracker)
            self.log.info(
                "Filtering for metafiles with tracker %r...",
                filter_url_prefix,
            )
        if self.options.reannounce_all:
            self.options.reannounce = self.options.reannounce_all
        else:
            # When changing the announce URL w/o changing the domain, don't change the info hash!
            self.options.no_cross_seed = True

        # Resolve tracker alias, if URL doesn't look like an URL
        if (
            self.options.reannounce
            and not urllib.parse.urlparse(self.options.reannounce).scheme
        ):
            for conn in config.multi_connection_lookup(self.options.reannounce):
                if urllib.parse.urlparse(conn).scheme:
                    self.options.reannounce = conn
                    break
            else:
                raise error.UserError(
                    "Unknown tracker alias or URL %r!" % (self.options.reannounce)
                )

        # go through given files
        bad = 0
        changed = 0
        for filename in self.options.metafile:
            try:
                # Read and remember current content
                torrent: metafile.Metafile = metafile.Metafile.from_file(Path(filename))
            except (OSError, KeyError, bencode.BencodeDecodeError) as exc:
                # There is no way to recover from this
                self.log.warning(
                    "Skipping bad bencode file %r (%s: %s)",
                    filename,
                    type(exc).__name__,
                    exc,
                )
                bad += 1
                continue

            # Check metafile integrity
            if not self.options.no_validation:
                try:
                    torrent.check_meta()
                except ValueError as exc:
                    self.log.warning(
                        "Metafile %r failed pre-change integrity check: %s",
                        filename,
                        exc,
                    )
                    bad += 1
                    continue

            if self.options.check_data:
                # pylint: disable=import-outside-toplevel
                from pyrosimple.util.metafile import PieceLogger
                from pyrosimple.util.ui import HashProgressBar, HashProgressBarCounter

                with HashProgressBar() as pb:
                    if (
                        logging.getLogger(__name__).isEnabledFor(logging.WARNING)
                        and sys.stdout.isatty()
                    ):
                        progress_callback = cast(
                            HashProgressBarCounter, pb()
                        ).progress_callback
                    else:
                        progress_callback = None

                    piece_logger = PieceLogger(torrent, self.log)

                    data_correct = torrent.hash_check(
                        Path(self.options.check_data),
                        progress_callback=progress_callback,
                        piece_callback=piece_logger.check_piece,
                    )
                if not data_correct:
                    self.log.error(
                        "File %s does match data from %s",
                        filename,
                        self.options.check_data,
                    )
                    sys.exit(error.EX_DATAERR)

            # Skip any metafiles that don't meet the pre-conditions
            if (
                filter_url_prefix
                and config.map_announce2alias(torrent["announce"]) != filter_url_prefix
            ):
                self.log.info(
                    "Skipping metafile %r: not tracked by %r!",
                    filename,
                    filter_url_prefix,
                )
                continue

            # Keep resume info safe
            libtorrent_resume = {}
            if "libtorrent_resume" in torrent:
                try:
                    libtorrent_resume["bitfield"] = torrent["libtorrent_resume"][
                        "bitfield"
                    ]
                except KeyError:
                    pass  # nothing to remember

                libtorrent_resume["files"] = copy.deepcopy(
                    torrent["libtorrent_resume"]["files"]
                )

            # Change private flag?
            if self.options.make_private and not torrent["info"].get("private", 0):
                self.log.info("Setting private flag...")
                torrent["info"]["private"] = 1
            if self.options.make_public and torrent["info"].get("private", 0):
                self.log.info("Clearing private flag...")
                del torrent["info"]["private"]

            # Remove non-standard keys?
            if self.options.clean or self.options.clean_all or self.options.clean_xseed:
                torrent.clean_meta(
                    including_info=not self.options.clean,
                )

            # Restore resume info?
            if self.options.clean_xseed:
                if libtorrent_resume:
                    self.log.info("Restoring key 'libtorrent_resume'...")
                    torrent.setdefault("libtorrent_resume", {})
                    torrent["libtorrent_resume"].update(libtorrent_resume)
                else:
                    self.log.warning("No resume information found!")

            # Clean rTorrent data?
            if self.options.clean_rtorrent:
                for key in self.RT_RESUME_KEYS:
                    if key in torrent:
                        self.log.info("Removing key %r...", key)
                        del torrent[key]

            # Change announce URL?
            if self.options.reannounce:
                torrent["announce"] = self.options.reannounce
                if "announce-list" in torrent:
                    del torrent["announce-list"]

                if not self.options.no_cross_seed:
                    # Enforce unique hash per tracker
                    torrent["info"]["x_cross_seed"] = hashlib.md5(
                        self.options.reannounce.encode()
                    ).hexdigest()

            # Change comment or creation date?
            if self.options.comment is not None:
                if self.options.comment:
                    torrent["comment"] = self.options.comment
                elif "comment" in torrent:
                    del torrent["comment"]
            if self.options.bump_date:
                torrent["creation date"] = int(time.time())
            if self.options.no_date and "creation date" in torrent:
                del torrent["creation date"]

            # Add fast-resume data?
            if self.options.hashed:
                datadir: str = self.options.hashed
                if "{}" in datadir and not os.path.exists(datadir):
                    datadir = datadir.replace("{}", torrent["info"]["name"])
                try:
                    torrent.add_fast_resume(Path(datadir))
                except OSError as exc:
                    self.fatal("Error making fast-resume data (%s)", exc)
                    raise

            # Set specific keys?
            torrent.assign_fields(self.options.set)
            replace_fields(torrent, self.options.regex)

            # Validate the new data
            if not self.options.no_validation:
                try:
                    torrent.check_meta()
                except ValueError as exc:
                    self.log.warning(
                        "Metafile %r failed post-change integrity check: %s",
                        filename,
                        exc,
                    )
                    bad += 1
                    continue

            # Write new metafile, if changed
            if self.options.output_directory:
                filename = Path(
                    self.options.output_directory, os.path.basename(filename)
                )
                self.log.info("Will write %r...", filename)

                if not self.options.dry_run:
                    torrent.save(filename)
                    if "libtorrent_resume" in torrent:
                        # Also write clean version
                        filename = Path(
                            str(filename).replace(".torrent", "-no-resume.torrent")
                        )
                        del torrent["libtorrent_resume"]
                        self.log.info("Writing '%s'...", filename)
                        torrent.save(filename)
            else:
                current_torrent = metafile.Metafile.from_file(filename)
                diff = diff_metafiles(current_torrent, torrent, filename)
                if self.options.diff:
                    sys.stdout.writelines(diff)
                if not diff:
                    self.log.info("No change to file %r", filename)
                    continue
                self.log.info("Changing %r...", filename)

                if not self.options.dry_run:
                    # Write to temporary file
                    tempname = os.path.join(
                        os.path.dirname(filename),
                        "." + os.path.basename(filename),
                    )
                    self.log.debug("Writing temporary file '%s'...", tempname)
                    torrent.save(Path(tempname))

                    try:
                        self.log.debug("Replacing file '%s'...", filename)
                        os.replace(tempname, filename)
                    except OSError as exc:
                        # TODO: Try to write directly, keeping a backup!
                        raise error.LoggableError(
                            "Can't rename tempfile %r to %r (%s)"
                            % (tempname, filename, exc)
                        )

            changed += 1

        # Print summary
        if changed:
            self.log.info(
                "%s %d metafile(s).",
                "Would've changed" if self.options.dry_run else "Changed",
                changed,
            )
        if bad:
            self.log.warning("Skipped %d bad metafile(s)!", bad)


def run():  # pragma: no cover
    """The entry point."""
    MetafileChanger().run()


if __name__ == "__main__":
    run()
