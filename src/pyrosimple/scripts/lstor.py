""" Metafile Lister.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import hashlib
import json

import bencode

from pyrosimple.scripts.base import ScriptBase
from pyrosimple.util import metafile


class MetafileLister(ScriptBase):
    """List contents of a bittorrent metafile."""

    # argument description for the usage information
    ARGS_HELP = "<metafile>..."

    def add_options(self):
        """Add program options."""
        self.add_bool_option("--reveal", help="show full announce URL including keys")
        self.add_bool_option(
            "--raw", help="print the metafile's raw content in all detail"
        )
        self.add_bool_option(
            "-V",
            "--skip-validation",
            help="show broken metafiles with an invalid structure",
        )
        self.add_value_option(
            "-o",
            "--output",
            "KEY,KEY1.KEY2,...",
            action="append",
            default=[],
            help="select fields to print, output is separated by TABs;"
            " note that __file__ is the path to the metafile,"
            " __hash__ is the info hash,"
            " and __size__ is the data size in bytes",
        )
        # TODO: implement this
        # self.add_value_option("-c", "--check-data", "PATH",
        #    help="check the hash against the data in the given path")

    def mainloop(self):
        """The main loop."""
        if not self.args:
            self.parser.print_help()
            self.parser.exit()

        for idx, filename in enumerate(self.args):
            torrent = metafile.Metafile(filename)
            if idx and not self.options.output and not self.options.raw:
                print()
                print("~" * 79)

            try:
                # Read and check metafile
                try:
                    data = metafile.checked_open(
                        filename,
                        log=self.LOG if self.options.skip_validation else None,
                    )
                except OSError as exc:
                    self.fatal(
                        "Can't read '%s' (%s)"
                        % (
                            filename,
                            str(exc).replace(": '%s'" % filename, ""),
                        )
                    )
                    raise

                listing = None

                if self.options.raw:
                    if not self.options.reveal and "info" in data:
                        # Shorten useless binary piece hashes
                        data["info"]["pieces"] = "<%d piece hashes>" % (
                            len(data["info"]["pieces"]) / len(hashlib.sha1().digest())
                        )

                    class BencodeJSONEncoder(json.JSONEncoder):
                        """Small helper class to translate 'binary' strings"""

                        def default(self, o):
                            if isinstance(o, bytes):
                                return o.hex().upper()
                            return super().default(o)

                    listing = BencodeJSONEncoder(indent=2).encode(data)
                elif self.options.output:

                    def splitter(fields):
                        "Yield single names for a list of comma-separated strings."
                        for flist in fields:
                            for field in flist.split(","):
                                yield field.strip()

                    data["__file__"] = filename
                    if "info" in data:
                        data["__hash__"] = metafile.info_hash(data)
                        data["__size__"] = metafile.data_size(data)
                    values = []
                    for field in splitter(self.options.output):
                        try:
                            val = data
                            for key in field.split("."):
                                val = val[key]
                        except KeyError as exc:
                            self.LOG.error(
                                "%s: Field %r not found (%s)", filename, field, exc
                            )
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
