""" Metafile Support.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import copy
import errno
import hashlib
import logging
import math
import os
import re
import time
import urllib

from pathlib import Path, PurePath
from typing import (
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
    cast,
)

import bencode  # typing: ignore

from pyrosimple import error
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

# PieceLogger and PieceFailer are both utility classes for passing
# into Metafile.make_info()'s piece_callback.
class PieceLogger:
    """Holds some state to display useful error messages
    if pieces fail to hash check"""

    def __init__(self, meta, logger=None):
        self.piece_index = 0
        self.meta = meta
        if logger is None:
            self.log = logging.getLogger(__name__)
        else:
            self.log = logger

    def check_piece(self, filename: os.PathLike, piece: bytes):
        "Callback for new piece"
        if (
            piece
            != self.meta["info"]["pieces"][self.piece_index : self.piece_index + 20]
        ):
            self.log.warning(
                "Piece #%d: Hashes differ in file %s",
                self.piece_index // 20,
                filename,
            )
        self.piece_index += 20


class PieceFailer(PieceLogger):
    """Raises an OSError if any pieces don't match, with context on
    the piece and file that failed"""

    def check_piece(self, filename: os.PathLike, piece: bytes):
        "Callback for new piece"
        if (
            piece
            != self.meta["info"]["pieces"][self.piece_index : self.piece_index + 20]
        ):
            raise OSError(
                f"Piece #{self.piece_index // 20}: Hashes differ in file '{filename}'"
            )
        self.piece_index += 20


def mask_keys(announce_url: str) -> str:
    """Mask any passkeys (hex sequences) in an announce URL."""
    return PASSKEY_RE.sub(
        lambda m: m.group() if m.group() in PASSKEY_OK else "*" * len(m.group()),
        announce_url,
    )


class Metafile(dict):
    """A torrent metafile, representing structure and operations for a .torrent file."""

    @staticmethod
    def from_file(filename: Path):
        """Load a metafile directly from a file."""
        with filename.open("rb") as handle:
            raw_data = handle.read()
        return Metafile(bencode.decode(raw_data))

    @property
    def is_multi_file(self) -> bool:
        """Provide a standard way to detect if metafile contains
        multiple files"""
        if "length" in self["info"]:
            return False
        return True

    def dict_copy(self) -> Dict:
        """Provide a copy of the metafile as a pure dict"""
        return copy.deepcopy(dict(self))

    def save(self, filename: Path) -> None:
        """Save the metafile to an actual file."""
        with filename.open("wb") as handle:
            handle.write(bencode.encode(dict(self)))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = pymagic.get_class_logger(self)
        self.ignore = []

    def check_info(self) -> None:
        """Validate info dict.

        Raise ValueError if validation fails.
        """

        def assert_value(cond, error_str):
            """Helper method to reduce boilerplate"""
            if not bool(cond):
                raise ValueError(f"bad metainfo - {error_str}")

        # The `cast` calls here are just to satisfy mypy's type checking
        info = cast(Dict, self.get("info"))
        assert_value(isinstance(info, dict), "not a dict")
        pieces = cast(bytes, info.get("pieces"))
        assert_value(isinstance(pieces, bytes), "pieces key is not data")
        assert_value(len(pieces) % 20 == 0, "pieces not in multiples of 20")
        piece_size = cast(int, info.get("piece length"))
        assert_value(
            isinstance(piece_size, int) and piece_size > 0, "illegal piece length"
        )
        name = cast(str, info.get("name"))
        assert_value(
            isinstance(name, str), f"bad name (type is {type(name).__name__!r})"
        )
        assert_value(
            ALLOWED_ROOT_NAME.match(name),
            f"name {name!r} disallowed for security reasons",
        )
        assert_value(
            len(set(info.keys()) & {"length", "files"}) != 2, "single/multiple file mix"
        )
        if "length" in info:
            length = cast(int, info.get("length"))
            assert_value(isinstance(length, int) or length < 0, "bad length")
        else:
            files = cast(List, info.get("files"))
            assert_value(isinstance(files, (list, tuple)), "bad file list")
            path_set = set()
            for item in files:
                assert_value(isinstance(item, dict), "bad file value")
                length = item.get("length")
                assert_value(isinstance(length, int) or length < 0, "bad file length")
                path = item.get("path")
                assert_value(path, "empty path")
                assert_value(isinstance(path, (list, tuple)), "bad path")
                for part in path:
                    assert_value(isinstance(part, str), "bad path dir")
                    assert_value(
                        part != "..",
                        f"relative path in {path!r} disallowed for security reasons",
                    )
                    if part:
                        assert_value(
                            ALLOWED_PATH_NAME.match(part),
                            f"part {part!r} of path {path!r} disallowed for security reasons",
                        )
                full_path = os.sep.join(path)
                assert_value(full_path not in path_set, f"duplicate path {full_path!r}")
                path_set.add(full_path)

    def check_meta(self) -> None:
        """Validate meta dict.

        Raise ValueError if validation fails.
        """
        if not isinstance(self.get("announce"), str):
            raise ValueError("bad announce URL - not a string")
        if not isinstance(self.get("info"), dict):
            raise ValueError("bad info key - not a dictionary")
        self.check_info()

    def info_hash(self) -> str:
        """Return info hash as a string."""
        return hashlib.sha1(bencode.encode(self["info"])).hexdigest().upper()

    def walk(self, datapath: Path) -> Generator[Path, None, None]:
        """Generate paths from "datapath", ignoring files/dirs as necessary"""
        if datapath.is_dir():
            # Walk the directory tree. `path.rglob` is not suitable
            # here due to how the blacklisting happens
            for dirpath, dirnames, filenames in os.walk(datapath):
                # Don't scan blacklisted directories
                for bad in dirnames[:]:
                    if any(pattern.match(bad) for pattern in self.ignore):
                        dirnames.remove(bad)

                # Yield all filenames that aren't blacklisted
                for filename in filenames:
                    if not any(pattern.match(filename) for pattern in self.ignore):
                        yield Path(dirpath, filename)
        else:
            if not any(pattern.match(str(datapath)) for pattern in self.ignore):
                yield Path(datapath)

    def _calc_size(self, datapath) -> int:
        """Get total size of a path."""
        return sum(os.path.getsize(filename) for filename in self.walk(datapath))

    def _make_info(
        self,
        files: Sequence[os.PathLike],
        piece_size: int,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        piece_callback: Optional[Callable[[os.PathLike, bytes], None]] = None,
        datapath: Optional[Path] = None,
    ) -> Tuple[Dict, int]:
        """Create info dict from a list of files."""
        # These collect the file descriptions and piece hashes
        file_list = []
        pieces = []

        # Initialize progress state
        hashing_secs = time.time()
        totalsize: int = sum(Path(filename).stat().st_size for filename in files)
        totalhashed: int = 0

        # Start a new piece
        sha1sum = hashlib.sha1()
        done: int = 0
        filename = None
        if datapath is None:
            datapath = os.path.commonpath(files)

        # Hash all files
        for filename in files:
            # Assemble file info
            filepath = Path(filename)
            filesize = filepath.stat().st_size
            rel_filepath = filepath.relative_to(datapath)
            file_list.append(
                {
                    "length": filesize,
                    "path": PurePath(rel_filepath).parts,
                }
            )
            self.log.debug("Hashing '%s', size %d...", filepath, filesize)

            # Open file and hash it
            fileoffset = 0
            with filepath.open("rb") as handle:
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
                    if progress_callback:
                        progress_callback(totalhashed, totalsize)

        # Add hash of partial last piece
        if done > 0:
            pieces.append(sha1sum.digest())
            if piece_callback:
                piece_callback(filepath, pieces[-1])

        # Build the meta dict
        metainfo = {
            "pieces": b"".join(pieces),
            "piece length": piece_size,
            "name": os.path.basename(datapath),
        }

        # Handle directory/FIFO vs. single file
        if os.path.isdir(datapath):
            metainfo["files"] = file_list
        else:
            metainfo["length"] = totalhashed

        hashing_secs = time.time() - hashing_secs
        self.log.debug(
            "Hashing of %s took %.1f secs (%s/s)",
            fmt.human_size(totalhashed).strip(),
            hashing_secs,
            fmt.human_size(totalhashed / hashing_secs).strip(),
        )

        # Return validated info dict
        return metainfo, totalhashed

    def sanitize(self) -> Tuple[Set, Set]:
        """Try to fix common problems. In particular, try to transcode
        non-standard string encodings.
        """
        bad_encodings, bad_fields = set(), set()

        def sane_encoding(field, text) -> bytes:
            "Transcoding helper."
            if isinstance(text, str):
                return text.encode("utf-8")
            for encoding in ("utf-8", self.get("encoding", None), "cp1252"):
                if encoding:
                    try:
                        u8_text: bytes = text.decode(encoding).encode("utf-8")
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
            if field in self.keys():
                self[field] = sane_encoding(field, self[field])

        self["info"]["name"] = sane_encoding("info name", self["info"]["name"])

        for entry in self["info"].get("files", []):
            entry["path"] = [sane_encoding("file path", i) for i in entry["path"]]

        return bad_encodings, bad_fields

    def assign_fields(self, assignments: List[str]) -> None:
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

                namespace = self
                # TODO: Allow numerical indices, and "+" for append
                keypath = [
                    i.replace("\0", ".") for i in field.replace("..", "\0").split(".")
                ]
                for key in keypath[:-1]:
                    # Create missing dicts as we go...
                    namespace = namespace.setdefault(key, {})
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise error.UserError(
                    f"Bad assignment {assignment!r} ({exc})!"
                ) from exc
            else:
                if val is None:
                    del namespace[keypath[-1]]
                else:
                    namespace[keypath[-1]] = val

    def add_fast_resume(self, datapath: Path) -> None:
        """Add fast resume data to a metafile dict."""
        # Get list of files
        files = self["info"].get("files", None)
        if not self.is_multi_file:
            if datapath.is_dir():
                datapath = datapath.joinpath(self["info"]["name"])
            files = [
                Bunch(
                    path=[os.path.abspath(datapath)],
                    length=self["info"]["length"],
                )
            ]

        # Prepare resume data
        resume = self.setdefault("libtorrent_resume", {})
        resume["bitfield"] = len(self["info"]["pieces"]) // 20
        resume["files"] = []
        piece_length = self["info"]["piece length"]
        offset = 0

        for fileinfo in files:
            # Get the path into the filesystem
            filepath = Path(*fileinfo["path"])
            if self.is_multi_file:
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
        self["libtorrent_resume"] = resume

    def data_size(self) -> int:
        """Calculate the size of a torrent based on parsed metadata."""
        info = self["info"]

        if not self.is_multi_file:
            # Single file
            return int(info["length"])
        # Directory structure
        return sum(f["length"] for f in info["files"])

    def _make_meta(
        self,
        datapath: Path,
        tracker_url: str,
        root_name: str,
        private: bool,
        progress: Optional[Callable[[int, int], None]] = None,
        piece_size: int = 0,
        piece_size_min: int = 2**15,
        piece_size_max: int = 2**24,
    ) -> Tuple[Dict, int]:
        """Create torrent dictionary from a file path."""
        if piece_size <= 0:
            # Calculate a good size for the data
            piece_size_exp = int(math.log(self._calc_size(datapath)) / math.log(2)) - 9
            # Limit it to the min and max
            piece_size = min(piece_size_max, max(piece_size_min, 2**piece_size_exp))
        # Round to the nearest power of two for all use cases
        piece_size = 2 ** (int(math.ceil(math.log(piece_size) / math.log(2))))

        # Build info hash
        info, totalhashed = self._make_info(
            sorted(self.walk(datapath)),
            piece_size,
            progress_callback=progress,
            datapath=datapath,
        )

        # Set private flag
        if private:
            info["private"] = 1

        # Freely chosen root name (default is basename of the data path)
        if root_name:
            info["name"] = root_name

        # Torrent metadata
        self["info"] = info
        self["announce"] = tracker_url.strip()

        # Return validated meta dict
        self.check_meta()
        return self, totalhashed

    def clean_meta(self, including_info: bool = False) -> Set[str]:
        """Clean meta dict.

        @param logger: If given, a callable accepting a string message.
        @return: Set of keys removed from C{meta}.
        """
        modified: Set[str] = set()

        for key in list(self.keys()):
            if [key] not in METAFILE_STD_KEYS:
                del self[key]
                modified.add(key)

        if including_info:
            for key in list(self["info"].keys()):
                if ["info", key] not in METAFILE_STD_KEYS:
                    del self["info"][key]
                    modified.add("info." + key)

            for entry in list(self["info"].get("files", [])):
                for key in list(entry.keys()):
                    if ["info", "files", key] not in METAFILE_STD_KEYS:
                        del entry[key]
                        modified.add("info.files." + key)

                # Remove crap that certain PHP software puts in paths
                entry["path"] = [i for i in entry["path"] if i]

        return modified

    @staticmethod
    def from_path(
        datapath,
        tracker_url,
        comment=None,
        root_name=None,
        created_by=None,
        private: bool = False,
        no_date: bool = False,
        progress=None,
        ignore=None,
        piece_size: int = 0,
        piece_size_min: int = 2**15,
        piece_size_max: int = 2**24,
    ):
        """Create a metafile with the path given on object creation.
        Returns the last metafile dict that was written (as an object, not bencoded).
        """
        # Lookup announce URLs from config file
        torrent = Metafile()
        if ignore:
            torrent.ignore = ignore
        try:
            if urllib.parse.urlparse(tracker_url).scheme:
                tracker_alias = (
                    urllib.parse.urlparse(tracker_url).netloc.split(":")[0].split(".")
                )
                tracker_alias = tracker_alias[-2 if len(tracker_alias) > 1 else 0]
            else:
                from pyrosimple import config  # pylint: disable=import-outside-toplevel

                tracker_alias, tracker_url = config.lookup_announce_url(tracker_url)
                tracker_url = tracker_url[0]
        except (KeyError, IndexError) as exc:
            raise error.UserError(
                f"Bad tracker URL {tracker_url!r}, or unknown alias!"
            ) from exc

        meta, _ = torrent._make_meta(
            datapath,
            tracker_url,
            root_name,
            private,
            progress,
            piece_size,
            piece_size_min,
            piece_size_max,
        )

        # Add optional fields
        if comment:
            meta["comment"] = comment
        if created_by:
            meta["created by"] = created_by
        if not no_date:
            meta["creation date"] = int(time.time())
        return Metafile(meta)

    def hash_check(
        self, datapath: Path, progress_callback=None, piece_callback=None
    ) -> bool:
        """Check piece hashes of a metafile against the given datapath."""

        if self.is_multi_file:
            files = [Path(datapath, *i["path"]) for i in self["info"]["files"]]
        else:
            if datapath.is_dir():
                datapath = datapath.joinpath(self["info"]["name"])
            files = [datapath]
        datameta, _ = self._make_info(
            files,
            int(self["info"]["piece length"]),
            progress_callback=progress_callback,
            piece_callback=piece_callback,
        )
        return bool(datameta["pieces"] == self["info"]["pieces"])

    def listing(self, masked=True) -> List[str]:
        """List torrent info & contents in human-readable format. Returns a list of formatted lines."""
        # Assemble data
        bad_encodings: List[str] = []
        bad_fields: List[str] = []
        announce = str(self["announce"])
        if masked:
            announce = mask_keys(announce)
        info = self["info"]
        infohash = self.info_hash()

        total_size = self.data_size()
        piece_length = info["piece length"]
        piece_number, last_piece_length = divmod(total_size, piece_length)

        # Build result
        if "creation date" in self and self["creation date"]:
            creation_date = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(self["creation date"])
            )
        else:
            creation_date = "N/A"
        result: List[str] = [
            f"NAME {self['info']['name']}",
            "SIZE %s (%i * %s + %s)"
            % (
                fmt.human_size(total_size).strip(),
                piece_number,
                fmt.human_size(piece_length).strip(),
                fmt.human_size(last_piece_length).strip(),
            ),
            "META %s (pieces %s %.1f%%)"
            % (
                fmt.human_size(self.data_size()).strip(),
                fmt.human_size(len(info["pieces"])).strip(),
                100.0 * len(info["pieces"]) / self.data_size(),
            ),
            f"HASH {infohash.upper()}",
            f"URL  {announce}",
            "PRV  %s"
            % (
                "YES (DHT/PEX disabled)"
                if info.get("private")
                else "NO (DHT/PEX enabled)"
            ),
            "TIME %s" % creation_date,
        ]

        for label, key in (("BY  ", "created by"), ("REM ", "comment")):
            if key in self:
                result.append(f"{label} {self.get(key, 'N/A')}")

        result.extend(
            [
                "",
                "FILE LISTING%s"
                % (
                    ""
                    if not self.is_multi_file
                    else " [%d file(s)]" % len(info["files"]),
                ),
            ]
        )
        if not self.is_multi_file:
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
