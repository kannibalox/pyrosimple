""" Metafile Support.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import errno
import fnmatch
import hashlib
import logging
import math
import os
import pprint
import re
import sys
import time
import urllib

from pathlib import Path, PurePath
from typing import Callable, Dict, Generator, List, Optional, Union

import bencode  # typing: ignore

from pyrosimple import config, error
from pyrosimple.util import fmt, pymagic
from pyrosimple.util.parts import Bunch


ALLOWED_ROOT_NAME = re.compile(
    r"^[^/\\.~][^/\\]*$"
)  # cannot be absolute or ~user, and cannot have path parts
ALLOWED_PATH_NAME = re.compile(r"^(?:~\d+)?[^/\\~][^/\\]*$")


PASSKEY_RE = re.compile(r"(?<=[/=])[-_0-9a-zA-Z]{5,64}={0,3}(?=[/&]|$)")


PASSKEY_OK = (
    "announce",
    "TrackerServlet",
)


METAFILE_STD_KEYS = [
    _i.split(".")
    for _i in (
        "announce",
        "announce-list",  # BEP-0012
        "comment",
        "created by",
        "creation date",
        "encoding",
        "info",
        "info.length",
        "info.name",
        "info.piece length",
        "info.pieces",
        "info.private",
        "info.files",
        "info.files.length",
        "info.files.path",
    )
]


def console_progress():
    """Return a progress indicator for consoles if
    stdout is a tty.
    """

    def progress(totalhashed, totalsize):
        "Helper"
        msg = " " * 30
        if totalhashed < totalsize:
            msg = f"{totalhashed * 100.0 / totalsize:5.1f}% complete"
        sys.stdout.write(msg + " \r")
        sys.stdout.flush()

    try:
        return progress if sys.stdout.isatty() else None
    except AttributeError:
        return None


def mask_keys(announce_url: str) -> str:
    """Mask any passkeys (hex sequences) in an announce URL."""
    return PASSKEY_RE.sub(
        lambda m: m.group() if m.group() in PASSKEY_OK else "*" * len(m.group()),
        announce_url,
    )


class MaskingPrettyPrinter(pprint.PrettyPrinter):
    """A PrettyPrinter that masks strings in the object tree."""

    def format(
        self, obj, context, maxlevels, level
    ):  # pylint: disable=arguments-renamed
        """Mask obj if it looks like an URL, then pass it to the super class."""
        if isinstance(obj, str) and "://" in obj:
            obj = mask_keys(obj)
        return pprint.PrettyPrinter.format(self, obj, context, maxlevels, level)


def check_info(info):
    """Validate info dict.

    Raise ValueError if validation fails.
    """
    if not isinstance(info, dict):
        raise ValueError("bad metainfo - not a dictionary")

    pieces = info.get("pieces")
    if not isinstance(pieces, bytes) or len(pieces) % 20 != 0:
        raise ValueError("bad metainfo - bad pieces key")

    piece_size = info.get("piece length")
    if not isinstance(piece_size, int) or piece_size <= 0:
        raise ValueError("bad metainfo - illegal piece length")

    name = info.get("name")
    if not isinstance(name, str):
        raise ValueError(f"bad metainfo - bad name (type is {type(name).__name__!r})")
    if not ALLOWED_ROOT_NAME.match(name):
        raise ValueError(f"name {name} disallowed for security reasons")

    if ("files" in info) == ("length" in info):
        raise ValueError("single/multiple file mix")

    if "length" in info:
        length = info.get("length")
        if not isinstance(length, int) or length < 0:
            raise ValueError("bad metainfo - bad length")
    else:
        files = info.get("files")
        if not isinstance(files, (list, tuple)):
            raise ValueError("bad metainfo - bad file list")

        for item in files:
            if not isinstance(item, dict):
                raise ValueError("bad metainfo - bad file value")

            length = item.get("length")
            if not isinstance(length, int) or length < 0:
                raise ValueError("bad metainfo - bad length")

            path = item.get("path")
            if not isinstance(path, (list, tuple)) or not path:
                raise ValueError("bad metainfo - bad path")

            for part in path:
                if not isinstance(part, str):
                    raise ValueError("bad metainfo - bad path dir")
                if part == "..":
                    raise ValueError(
                        "relative path in %s disallowed for security reasons"
                        % "/".join(path)
                    )
                if part and not ALLOWED_PATH_NAME.match(part):
                    raise ValueError(f"path {part} disallowed for security reasons")

        file_paths = [os.sep.join(item["path"]) for item in files]
        if len(set(file_paths)) != len(file_paths):
            raise ValueError("bad metainfo - duplicate path")

    return info


def check_meta(meta):
    """Validate meta dict.

    Raise ValueError if validation fails.
    """
    if not isinstance(meta, dict):
        raise ValueError("bad metadata - not a dictionary")
    if not isinstance(meta.get("announce"), str):
        raise ValueError("bad announce URL - not a string")
    check_info(meta.get("info"))

    return meta


def clean_meta(meta: Dict, including_info: bool = False, logger=None):
    """Clean meta dict. Optionally log changes using the given logger.

    @param logger: If given, a callable accepting a string message.
    @return: Set of keys removed from C{meta}.
    """
    modified = set()

    for key in list(meta.keys()):
        if [key] not in METAFILE_STD_KEYS:
            if logger:
                logger(f"Removing key {key!r}...")
            del meta[key]
            modified.add(key)

    if including_info:
        for key in list(meta["info"].keys()):
            if ["info", key] not in METAFILE_STD_KEYS:
                if logger:
                    logger(f"Removing key {'info.' + key!r}...")
                del meta["info"][key]
                modified.add("info." + key)

        for idx, entry in enumerate(meta["info"].get("files", [])):
            for key in list(entry.keys()):
                if ["info", "files", key] not in METAFILE_STD_KEYS:
                    if logger:
                        logger("Removing key %r from file #%d..." % (key, idx + 1))
                    del entry[key]
                    modified.add("info.files." + key)

            # Remove crap that certain PHP software puts in paths
            entry["path"] = [i for i in entry["path"] if i]

    return modified


def sanitize(meta, diagnostics=False):
    """Try to fix common problems, especially transcode non-standard string encodings."""
    bad_encodings, bad_fields = set(), set()

    def sane_encoding(field, text):
        "Transcoding helper."
        if isinstance(text, str):
            return text.encode("utf-8")
        for encoding in ("utf-8", meta.get("encoding", None), "cp1252"):
            if encoding:
                try:
                    u8_text = text.decode(encoding).encode("utf-8")
                    if encoding != "utf-8":
                        bad_encodings.add(encoding)
                        bad_fields.add(field)
                    return u8_text
                except UnicodeError:
                    continue
        # Broken beyond anything reasonable
        bad_encodings.add("UNKNOWN/EXOTIC")
        bad_fields.add(field)
        return str(text, "utf-8", "replace").replace("\ufffd", "_").encode("utf-8")

    # Go through all string fields and check them
    for field in ("comment", "created by"):
        if field in meta:
            meta[field] = sane_encoding(field, meta[field])

    meta["info"]["name"] = sane_encoding("info name", meta["info"]["name"])

    for entry in meta["info"].get("files", []):
        entry["path"] = [sane_encoding("file path", i) for i in entry["path"]]

    return (meta, bad_encodings, bad_fields) if diagnostics else meta


def assign_fields(meta, assignments: List[str]):
    """Takes a list of C{key=value} strings and assigns them to the
    given metafile. If you want to set nested keys (e.g. "info.source"),
    you have to use a dot as a separator. For exotic keys *containing*
    a dot, double that dot ("dotted..key").

    Numeric values starting with "+" or "-" are converted to integers.

    If just a key name is given (no '='), the field is removed.
    """
    for assignment in assignments:
        try:
            val: Optional[Union[str, int]]
            if "=" in assignment:
                field, val = assignment.split("=", 1)
            else:
                field, val = assignment, None

            if val is not None and val[0] in "+-" and val[1:].isdigit():
                val = int(val, 10)

            # TODO: Allow numerical indices, and "+" for append
            namespace = meta
            keypath = [
                i.replace("\0", ".") for i in field.replace("..", "\0").split(".")
            ]
            for key in keypath[:-1]:
                # Create missing dicts as we go...
                namespace = namespace.setdefault(key, {})
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise error.UserError(f"Bad assignment {assignment!r} ({exc})!") from exc
        else:
            if val is None:
                del namespace[keypath[-1]]
            else:
                namespace[keypath[-1]] = val

    return meta


def add_fast_resume(meta, datapath: str):
    """Add fast resume data to a metafile dict."""
    # Get list of files
    files = meta["info"].get("files", None)
    single = files is None
    if single:
        if os.path.isdir(datapath):
            datapath = os.path.join(datapath, meta["info"]["name"])
        files = [
            Bunch(
                path=[os.path.abspath(datapath)],
                length=meta["info"]["length"],
            )
        ]

    # Prepare resume data
    resume = meta.setdefault("libtorrent_resume", {})
    resume["bitfield"] = len(meta["info"]["pieces"]) // 20
    resume["files"] = []
    piece_length = meta["info"]["piece length"]
    offset = 0

    for fileinfo in files:
        # Get the path into the filesystem
        filepath = Path(*fileinfo["path"])
        if not single:
            filepath = Path(datapath, filepath)

        # Check file size
        if os.path.getsize(filepath) != fileinfo["length"]:
            raise OSError(
                errno.EINVAL,
                "File size mismatch for %r [is %d, expected %d]"
                % (
                    filepath,
                    os.path.getsize(filepath),
                    fileinfo["length"],
                ),
            )

        # Add resume data for this file
        resume["files"].append(
            dict(
                priority=1,
                mtime=int(os.path.getmtime(filepath)),
                completed=(offset + fileinfo["length"] + piece_length - 1)
                // piece_length
                - offset // piece_length,
            )
        )
        offset += fileinfo["length"]

    return meta


def info_hash(metadata) -> str:
    """Return info hash as a string."""
    return hashlib.sha1(bencode.encode(metadata["info"])).hexdigest().upper()


def data_size(metadata) -> int:
    """Calculate the size of a torrent based on parsed metadata."""
    info = metadata["info"]

    if "length" in info:
        # Single file
        return int(info["length"])
    # Directory structure
    return sum(f["length"] for f in info["files"])


def checked_open(filename: str, log: logging.Logger = None):
    """Open and validate the given metafile.
    Optionally provide diagnostics on the passed logger, for
    invalid metafiles, which then just cause a warning but no exception.
    "quiet" can supress that warning.
    """
    with open(filename, "rb") as handle:
        raw_data = handle.read()
    data: Dict = bencode.decode(raw_data)

    try:
        check_meta(data)
        if raw_data != bencode.encode(data):
            raise ValueError("Bad bencoded data - dict keys out of order?")
    except ValueError as exc:
        if log:
            log.warning(f"{filename}: {exc}")
        else:
            raise

    return data


class Metafile:
    """A torrent metafile."""

    # Patterns of names to ignore
    IGNORE_GLOB = [
        "core",
        "CVS",
        ".*",
        "*~",
        "*.swp",
        "*.tmp",
        "*.bak",
        "[Tt]humbs.db",
        "[Dd]esktop.ini",
        "ehthumbs_vista.db",
    ]

    def __init__(self, filename, datapath=None):
        """Initialize metafile."""
        self.filename = filename
        self.progress = None
        self.datapath = datapath
        self._datapath = None
        self.ignore = self.IGNORE_GLOB[:]
        self.LOG = pymagic.get_class_logger(self)

    def _get_datapath(self):
        """Get a valid datapath, else raise an exception."""
        if self._datapath is None:
            raise OSError(
                errno.ENOENT, f"You didn't provide any datapath for {self.filename!r}"
            )

        return self._datapath

    def _set_datapath(self, datapath: str):
        """Set a datapath."""
        if datapath:
            self._datapath = datapath.rstrip(os.sep)
        else:
            self._datapath = None

    datapath = property(_get_datapath, _set_datapath)

    def walk(self) -> Generator[Path, None, None]:
        """Generate paths in "self.datapath"."""
        # Directory?
        if os.path.isdir(self.datapath):
            # Walk the directory tree
            for dirpath, dirnames, filenames in os.walk(
                self.datapath
            ):  # , followlinks=True):
                # Don't scan blacklisted directories
                for bad in dirnames[:]:
                    if any(fnmatch.fnmatch(bad, pattern) for pattern in self.ignore):
                        dirnames.remove(bad)

                # Yield all filenames that aren't blacklisted
                for filename in filenames:
                    if not any(
                        fnmatch.fnmatch(filename, pattern) for pattern in self.ignore
                    ):
                        yield Path(dirpath, filename)

        # Single file
        else:
            # Yield the filename
            yield Path(self.datapath)

    def _calc_size(self) -> int:
        """Get total size of "self.datapath"."""
        return sum(os.path.getsize(filename) for filename in self.walk())

    def _make_info(self, piece_size: int, progress, walker, piece_callback=None):
        """Create info dict."""
        # These collect the file descriptions and piece hashes
        file_list = []
        pieces = []

        # Initialize progress state
        hashing_secs = time.time()
        totalsize = self._calc_size()
        totalhashed = 0

        # Start a new piece
        sha1sum = hashlib.sha1()
        done = 0
        filename = None

        # Hash all files
        for filename in walker:
            # Assemble file info
            filepath = Path(filename)
            filesize = filepath.stat().st_size
            filepath = filepath.relative_to(self.datapath)
            file_list.append(
                {
                    "length": filesize,
                    "path": PurePath(filepath).parts,
                }
            )
            self.LOG.debug("Hashing '%s', size %d...", filename, filesize)

            # Open file and hash it
            fileoffset = 0
            with open(filename, "rb") as handle:
                while fileoffset < filesize:
                    # Read rest of piece or file, whatever is smaller
                    chunk = handle.read(min(filesize - fileoffset, piece_size - done))
                    sha1sum.update(chunk)
                    done += len(chunk)
                    fileoffset += len(chunk)
                    totalhashed += len(chunk)

                    # Piece is done
                    if done == piece_size:
                        pieces.append(sha1sum.digest())
                        if piece_callback:
                            piece_callback(filename, pieces[-1])

                        # Start a new piece
                        sha1sum = hashlib.sha1()
                        done = 0

                    # Report progress
                    if progress:
                        progress(totalhashed, totalsize)

        # Add hash of partial last piece
        if done > 0:
            pieces.append(sha1sum.digest())
            if piece_callback:
                piece_callback(filename, pieces[-1])

        # Build the meta dict
        metainfo = {
            "pieces": b"".join(pieces),
            "piece length": piece_size,
            "name": os.path.basename(self.datapath),
        }

        # Handle directory/FIFO vs. single file
        if os.path.isdir(self.datapath):
            metainfo["files"] = file_list
        else:
            metainfo["length"] = totalhashed

        hashing_secs = time.time() - hashing_secs
        self.LOG.info(
            "Hashing of %s took %.1f secs (%s/s)",
            fmt.human_size(totalhashed).strip(),
            hashing_secs,
            fmt.human_size(totalhashed / hashing_secs).strip(),
        )

        # Return validated info dict
        return check_info(metainfo), totalhashed

    def _make_meta(
        self,
        tracker_url: str,
        root_name: str,
        private: bool,
        progress: Optional[Callable] = None,
        piece_size: int = 0,
    ):
        """Create torrent dict."""
        if piece_size <= 0:
            total_size = self._calc_size()
            if total_size:
                piece_size_exp = int(math.log(total_size) / math.log(2)) - 9
            else:
                piece_size_exp = 0

            piece_size_exp = min(max(15, piece_size_exp), 24)
            piece_size = 2**piece_size_exp

        # Build info hash
        info, totalhashed = self._make_info(piece_size, progress, sorted(self.walk()))

        # Set private flag
        if private:
            info["private"] = 1

        # Freely chosen root name (default is basename of the data path)
        if root_name:
            info["name"] = root_name

        # Torrent metadata
        meta = {
            "info": info,
            "announce": tracker_url.strip(),
        }

        # Return validated meta dict
        return check_meta(meta), totalhashed

    def create(
        self,
        datapath,
        tracker_urls,
        comment=None,
        root_name=None,
        created_by=None,
        private: bool = False,
        no_date: bool = False,
        progress=None,
        callback=None,
    ):
        """Create a metafile with the path given on object creation.
        Returns the last metafile dict that was written (as an object, not bencoded).
        """
        if datapath:
            self.datapath = datapath

        try:
            tracker_urls = ["" + tracker_urls]
        except TypeError:
            tracker_urls = list(tracker_urls)
        multi_mode = len(tracker_urls) > 1

        # TODO add optimization so the hashing happens only once for multiple URLs!
        for tracker_url in tracker_urls:
            # Lookup announce URLs from config file
            try:
                if urllib.parse.urlparse(tracker_url).scheme:
                    tracker_alias = (
                        urllib.parse.urlparse(tracker_url)
                        .netloc.split(":")[0]
                        .split(".")
                    )
                    tracker_alias = tracker_alias[-2 if len(tracker_alias) > 1 else 0]
                else:
                    tracker_alias, tracker_url = config.lookup_announce_url(tracker_url)
                    tracker_url = tracker_url[0]
            except (KeyError, IndexError) as exc:
                raise error.UserError(
                    f"Bad tracker URL {tracker_url!r}, or unknown alias!"
                ) from exc

            # Determine metafile name
            output_name = self.filename
            if multi_mode:
                # Add 2nd level of announce URL domain to metafile name
                output_name = list(os.path.splitext(output_name))
                try:
                    output_name[1:1] = "-" + tracker_alias
                except (IndexError,):
                    self.LOG.error("Malformed announce URL %r, skipping!", tracker_url)
                    continue
                output_name = "".join(output_name)

            # Hash the data
            self.LOG.info(
                "Creating %r from %r...",
                output_name,
                self.datapath,
            )
            meta, _ = self._make_meta(tracker_url, root_name, private, progress)

            # Add optional fields
            if comment:
                meta["comment"] = comment
            if created_by:
                meta["created by"] = created_by
            if not no_date:
                meta["creation date"] = int(time.time())
            if callback:
                callback(meta)

            # Write metafile to disk
            self.LOG.debug("Writing %r...", output_name)
            with open(output_name, "wb") as fh:
                fh.write(bencode.encode(meta))

        return meta

    def check(self, metainfo, datapath, progress=None):
        """Check piece hashes of a metafile against the given datapath."""
        if datapath:
            self.datapath = datapath

        def check_piece(filename, piece):
            "Callback for new piece"
            if (
                piece
                != metainfo["info"]["pieces"][
                    check_piece.piece_index : check_piece.piece_index + 20
                ]
            ):
                self.LOG.warning(
                    "Piece #%d: Hashes differ in file %r",
                    check_piece.piece_index // 20,
                    filename,
                )
            check_piece.piece_index += 20

        check_piece.piece_index = 0

        datameta, _ = self._make_info(
            int(metainfo["info"]["piece length"]),
            progress,
            [datapath]
            if "length" in metainfo["info"]
            else (
                os.path.join(*([datapath] + i["path"]))
                for i in metainfo["info"]["files"]
            ),
            piece_callback=check_piece,
        )
        return datameta["pieces"] == metainfo["info"]["pieces"]

    def listing(self, masked=True):
        """List torrent info & contents. Returns a list of formatted lines."""
        # Assemble data
        with open(self.filename, "rb") as fh:
            metainfo = bencode.decode(fh.read())
        bad_encodings = []
        bad_fields = []
        announce = metainfo["announce"]
        info = metainfo["info"]
        infohash = hashlib.sha1(bencode.encode(info))

        total_size = data_size(metainfo)
        piece_length = info["piece length"]
        piece_number, last_piece_length = divmod(total_size, piece_length)

        # Build result
        result: List[str] = [
            f"NAME {Path(self.filename).name}",
            "SIZE %s (%i * %s + %s)"
            % (
                fmt.human_size(total_size).strip(),
                piece_number,
                fmt.human_size(piece_length).strip(),
                fmt.human_size(last_piece_length).strip(),
            ),
            "META %s (pieces %s %.1f%%)"
            % (
                fmt.human_size(os.path.getsize(self.filename)).strip(),
                fmt.human_size(len(info["pieces"])).strip(),
                100.0 * len(info["pieces"]) / os.path.getsize(self.filename),
            ),
            f"HASH {infohash.hexdigest().upper()}",
            f"URL  {(mask_keys if masked else str)(announce)}",
            "PRV  %s"
            % (
                "YES (DHT/PEX disabled)"
                if info.get("private")
                else "NO (DHT/PEX enabled)"
            ),
            "TIME %s"
            % (
                "N/A"
                if "creation date" not in metainfo
                else time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(metainfo["creation date"])
                )
            ),
        ]

        for label, key in (("BY  ", "created by"), ("REM ", "comment")):
            if key in metainfo:
                result.append(f"{label} {metainfo.get(key, 'N/A')}")

        result.extend(
            [
                "",
                "FILE LISTING%s"
                % ("" if "length" in info else " [%d file(s)]" % len(info["files"]),),
            ]
        )
        if "length" in info:
            # Single file
            result.append(
                "%-69s%9s"
                % (
                    info["name"],
                    fmt.human_size(total_size),
                )
            )
        else:
            # Directory structure
            result.append(f"{info['name']}/")
            oldpaths = [None] * 99
            for entry in info["files"]:
                # Remove crap that certain PHP software puts in paths
                entry_path = [i for i in entry["path"] if i]

                for idx, item in enumerate(entry_path[:-1]):
                    if item != oldpaths[idx]:
                        result.append(f"{' ' * (4 * (idx + 1))}{item}/")
                        oldpaths[idx] = item
                result.append(
                    "%-69s%9s"
                    % (
                        " " * (4 * len(entry_path)) + entry_path[-1],
                        fmt.human_size(entry["length"]),
                    )
                )

        if bad_encodings:
            result.extend(
                [
                    "",
                    "WARNING: Bad encoding(s) {} in these fields: {}".format(
                        ", ".join(sorted(bad_encodings)), ", ".join(sorted(bad_fields))
                    ),
                    "Use the --raw option to inspect these encoding issues.",
                ]
            )

        return result
