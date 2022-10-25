""" Metafile Lister.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""

import hashlib
import json
import logging
import sys

from pathlib import Path

import bencode

from pyrosimple.scripts.base import ScriptBase


class MetafileLister(ScriptBase):
    """List contents of a bittorrent metafile."""

    # argument description for the usage information
    ARGS_HELP = "<metafile>..."

    def add_options(self):
        """Add program options."""
        self.add_bool_option(
            "--reveal",
            help="show full announce URL including keys, as well as full piece information",
        )
        self.add_bool_option(
            "--raw", help="print the metafile's raw content in JSON format"
        )
        self.add_bool_option(
            "-V",
            "--skip-validation",
            help="show broken metafiles with an invalid structure",
        )
        self.add_value_option(
            "-o",
            "--output",
            "KEY1,KEY2.SUBKEY,...",
            action="append",
            default=[],
            help="select fields to print, output is separated by TABs;"
            " note that __file__ is the path to the metafile,"
            " __hash__ is the info hash,"
            " and __size__ is the data size in bytes",
        )
        self.add_value_option(
            "-c",
            "--check-data",
            "PATH",
            help="check the hash against the data in the given path",
        )

    def mainloop(self):
        """The main loop."""
        from pyrosimple.util import metafile  # pylint: disable=import-outside-toplevel

        if not self.args:
            self.parser.print_help()
            self.parser.error("No metafiles given, nothing to do!")
            self.parser.exit()

        for idx, filename in enumerate(self.args):
            if idx and not self.options.output and not self.options.raw:
                print()
                print("~" * 79)

            try:
                # Read and check metafile
                try:
                    filename = Path(filename)
                    torrent = metafile.Metafile.from_file(filename)
                    if not self.options.skip_validation:
                        torrent.check_meta()
                except OSError as exc:
                    self.fatal(
                        "Can't read '%s' (%s)"
                        % (
                            filename,
                            str(exc).replace(": '%s'" % filename, ""),
                        )
                    )
                    raise

                if self.options.check_data:
                    # pylint: disable=import-outside-toplevel
                    from pyrosimple.util.ui import HashProgressBar

                    with HashProgressBar() as pb:
                        if (
                            logging.getLogger().isEnabledFor(logging.WARNING)
                            and sys.stdout.isatty()
                        ):
                            c = pb()
                            progress_callback = c.progress_callback
                        else:
                            progress_callback = None

                        torrent.hash_check(
                            Path(self.options.check_data),
                            progress_callback=progress_callback,
                        )
                listing = None

                if self.options.raw:
                    if not self.options.reveal and "info" in torrent:
                        # Shorten useless binary piece hashes
                        torrent["info"]["pieces"] = "<%d piece hashes>" % (
                            len(torrent["info"]["pieces"])
                            / len(hashlib.sha1().digest())
                        )

                    class BencodeJSONEncoder(json.JSONEncoder):
                        """Small helper class to translate 'binary' strings"""

                        def default(self, o):
                            if isinstance(o, bytes):
                                return o.hex().upper()
                            return super().default(o)

                    listing = BencodeJSONEncoder(indent=2).encode(torrent)
                elif self.options.output:

                    def splitter(fields):
                        "Yield single names for a list of comma-separated strings."
                        for flist in fields:
                            for field in flist.split(","):
                                yield field.strip()

                    data = {}
                    data["__file__"] = filename
                    if "info" in torrent:
                        data["__hash__"] = torrent.info_hash()
                        data["__size__"] = torrent.data_size()
                    values = []
                    for field in splitter(self.options.output):
                        try:
                            if field in data:
                                val = data[field]
                            else:
                                val = dict(torrent)
                                for key in field.split("."):
                                    val = val[key]
                        except KeyError:
                            self.LOG.error("%s: Field %r not found", filename, field)
                            break
                        else:
                            values.append(str(val))
                    else:
                        listing = "\t".join(values)
                else:
                    listing = "\n".join(torrent.listing(masked=not self.options.reveal))
            except (ValueError, KeyError, bencode.BencodeDecodeError) as exc:
                self.LOG.error(
                    "Bad metafile %r (%s: %s)", filename, type(exc).__name__, exc
                )
                raise
            else:
                if listing is not None:
                    print(listing)


def run():  # pragma: no cover
    """The entry point."""
    ScriptBase.setup()
    MetafileLister().run()


if __name__ == "__main__":
    run()
