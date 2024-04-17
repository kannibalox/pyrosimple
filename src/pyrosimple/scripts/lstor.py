""" Metafile Lister.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""

import hashlib
import sys
import traceback

from pathlib import Path

import bencode

from pyrosimple.error import EX_DATAERR, EX_SOFTWARE
from pyrosimple.scripts.base import ScriptBase


class MetafileLister(ScriptBase):
    """List contents of a bittorrent metafile."""

    ENABLE_PROGRESS = True

    def add_options(self):
        """Add program options."""
        self.parser.add_argument("metafile", nargs="+", help="Torrent files to display")
        self.add_bool_option(
            "--reveal",
            help="show full announce URL including keys, as well as full piece information",
        )
        self.add_bool_option(
            "--raw", "--json", help="print the metafile's raw content in JSON format"
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

        self.args = self.options.metafile
        if not self.args:
            self.parser.print_help()
            self.parser.error("No metafiles given, nothing to do!")
            self.parser.exit()

        validation_errors = (ValueError, KeyError, bencode.BencodeDecodeError)

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
                        try:
                            torrent.check_meta()
                        except validation_errors:
                            self.return_code = EX_SOFTWARE
                            raise
                except OSError as exc:
                    self.fatal(
                        "Can't read '%s' (%s)"
                        % (
                            filename,
                            str(exc).replace(": '%s'" % filename, ""),
                        )
                    )
                    raise

                display_nothing = bool(self.options.output == [""])  # i.e `-o ""`

                output_values = torrent.dict_copy()
                if not self.options.reveal:
                    # Shorten useless binary piece hashes
                    if "info" in output_values:
                        count = len(output_values["info"]["pieces"]) / len(
                            hashlib.sha1().digest()
                        )
                        output_values["info"]["pieces"] = f"<{count} piece hashes>"
                    if "piece layers" in output_values:
                        for layer, pieces in output_values["piece layers"].items():
                            count = len(pieces) / 16 * 1024 * 1024
                            output_values["piece layers"][
                                layer
                            ] = f"<{count} piece hashes>"
                if self.options.output and not display_nothing:
                    output_values = []

                    def splitter(fields):
                        "Yield single names for a list of comma-separated strings."
                        for flist in fields:
                            for field in flist.split(","):
                                yield field.strip()

                    data = {}
                    data["__file__"] = str(filename)
                    if "info" in torrent:
                        data["__hash__"] = torrent.info_hash()
                        data["__size__"] = torrent.data_size()

                    for field in splitter(self.options.output):
                        try:
                            if field in data:
                                val = data[field]
                            else:
                                val = torrent.fetch_field(field)
                                if val is None:
                                    raise KeyError()
                        except KeyError:
                            self.log.error("%s: Field %r not found", filename, field)
                            output_values.append(None)
                        else:
                            output_values.append(val)

                if display_nothing:
                    pass
                elif self.options.raw:
                    from pyrosimple.util.fmt import (  # pylint: disable=import-outside-toplevel
                        BencodeJSONEncoder,
                    )

                    print(BencodeJSONEncoder(indent=2).encode(output_values))
                elif self.options.output:
                    print(
                        "\t".join(
                            [str(o) if o is not None else "" for o in output_values]
                        )
                    )
                else:
                    try:
                        print(
                            "\n".join(torrent.listing(masked=not self.options.reveal))
                        )
                    except validation_errors as exc:
                        self.log.error(
                            "Bad metafile %r (%s: %s)",
                            str(filename),
                            type(exc).__name__,
                            exc,
                        )
                        print(traceback.format_exc(), end="")
                        if not self.options.skip_validation:
                            self.return_code = EX_SOFTWARE
                if self.options.check_data:
                    # pylint: disable=import-outside-toplevel

                    from pyrosimple.util.metafile import PieceFailer
                    from pyrosimple.util.ui import HashProgressBar

                    piece_logger = PieceFailer(torrent, self.log)
                    try:
                        if self.options.progress == "on":
                            with HashProgressBar() as pb:
                                progress_callback = pb().progress_callback

                                torrent.hash_check(
                                    Path(self.options.check_data),
                                    progress_callback=progress_callback,
                                    piece_callback=piece_logger.check_piece,
                                )
                        else:
                            torrent.hash_check(
                                Path(self.options.check_data),
                                piece_callback=piece_logger.check_piece,
                            )
                    except OSError as exc:
                        print(
                            f"ERROR: File {str(filename)!r} did not hash check: {exc}"
                        )
                        sys.exit(EX_DATAERR)
            except validation_errors as exc:
                self.log.error(
                    "Bad metafile %r (%s: %s)", str(filename), type(exc).__name__, exc
                )
                print(traceback.format_exc(), end="")
                if not self.options.skip_validation:
                    self.return_code = EX_SOFTWARE


def run():  # pragma: no cover
    """The entry point."""
    MetafileLister().run()


if __name__ == "__main__":
    run()
