"""Data Formatting.

Copyright (c) 2009, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import datetime
import json
import logging
import os
import re
import shlex
import time

from pathlib import Path
from pprint import pformat
from typing import Optional

from pyrosimple import torrent
from pyrosimple.util import pymagic


log = logging.getLogger(__name__)


def human_size(size: float) -> str:
    """Return a human-readable representation of a byte size.

    @param size: Number of bytes as an integer or string.
    @return: String of length 10 with the formatted result.
    """
    if isinstance(size, str):
        size = float(size, 10)

    if size < 0:
        return "-??? bytes"

    if size < 1024:
        return f"{int(size):4d} bytes".lstrip()

    rem = float(size)
    for unit in ("KiB", "MiB", "GiB", "TiB", "PiB"):
        rem /= 1024.0
        if rem < 1024:
            return f"{rem:6.1f} {unit}".lstrip()

    return f"{rem:6.1f} PiB".lstrip()


def fmt_shell(string: str) -> str:
    """Quote a string for use in shell scripts."""
    return shlex.quote(string)


def fmt_sz(intval: int) -> str:
    """Format a byte sized value."""
    try:
        return human_size(intval).rjust(10)
    except (ValueError, TypeError):
        return "N/A".rjust(10)


def fmt_iso(timestamp: float) -> str:
    """Format a UNIX timestamp to an ISO datetime string."""
    try:
        return iso_datetime(timestamp)
    except (ValueError, TypeError):
        return "N/A".rjust(len(iso_datetime(0)))


def fmt_duration(duration: int) -> str:
    """Format a duration value in seconds to a readable form."""
    try:
        return human_duration(float(duration), 0, 2, True)
    except (ValueError, TypeError):
        return "N/A".rjust(len(human_duration(0, 0, 2, True)))


def fmt_delta(timestamp) -> str:
    """Format a UNIX timestamp to a delta (relative to now)."""
    try:
        return human_duration(float(timestamp), precision=2, short=True)
    except (ValueError, TypeError):
        return "N/A".rjust(len(human_duration(0, precision=2, short=True)))


def fmt_pc(floatval: float):
    """Scale a ratio value to percent."""
    return round(float(floatval) * 100.0, 2)


def fmt_strip(val: str) -> str:
    """Strip leading and trailing whitespace."""
    return str(val).strip()


def fmt_subst(val, regex, subst):
    """Replace regex with string."""
    return re.sub(regex, subst, val)


def fmt_mtime(val: str) -> float:
    """Modification time of a path."""
    p = Path(str(val))
    if p.exists():
        return p.stat().st_mtime
    return 0.0


def fmt_pathbase(val: str) -> str:
    """Base name of a path."""
    return os.path.basename(val or "")


def fmt_pathname(val: str) -> str:
    """Base name of a path, without its extension."""
    return os.path.splitext(os.path.basename(val or ""))[0]


def fmt_raw(val):
    """A little magic to allow showing the raw value of a field in rtcontrol"""
    return val


def fmt_fmt(val, field):
    """Apply a field-specific formatter (if present)"""

    # If val is a RtorrentItem, fetch `field` from it before formatting. This
    # is to allow `d|fmt('is_private')` vs. the redundant `d.is_private|fmt('is_private')`.
    # Be aware that using the former in rtcontrol templates breaks the field auto-detection.
    if field not in torrent.engine.FIELD_REGISTRY:
        return val
    if isinstance(val, torrent.rtorrent.RtorrentItem):
        val = getattr(val, field)
    formatter = torrent.engine.FIELD_REGISTRY[field].formatter
    if formatter:
        return formatter(val)
    return val


def fmt_pathext(val: str) -> str:
    """Extension of a path (including the '.')."""
    return os.path.splitext(val or "")[1]


def fmt_pathdir(val: str):
    """Directory containing the given path."""
    return os.path.dirname(val or "")


def fmt_json(val):
    """JSON serialization."""
    return json.dumps(val, cls=pymagic.JSONEncoder)


def iso_datetime(timestamp: Optional[float] = None) -> str:
    """Convert UNIX timestamp to ISO datetime string.

    @param timestamp: UNIX epoch value (default: the current time).
    @return: Timestamp formatted as "YYYY-mm-dd HH:MM:SS".
    """
    if timestamp is None:
        timestamp = time.time()
    return datetime.datetime.fromtimestamp(timestamp).isoformat(" ")[:19]


def iso_datetime_optional(timestamp) -> str:
    """Convert UNIX timestamp to ISO datetime string, or "never".

    @param timestamp: UNIX epoch value.
    @return: Timestamp formatted as "YYYY-mm-dd HH:MM:SS", or "never" for false values.
    """
    if timestamp:
        return iso_datetime(timestamp)
    return "never"


def bytes_from_human(val: str) -> int:
    """Convert a human string to integer bytes. Follows the same logic
    as rtcontrol's byte filter"""
    units = dict(b=1, k=1024, m=1024**2, g=1024**3)
    lower_val = str(val).lower()
    if any(lower_val.endswith(i) for i in units):
        scale = units[lower_val[-1]]
        val = val[:-1]
    else:
        scale = 1
    return int(val) * scale


def human_duration(
    time1: float, time2: Optional[float] = None, precision: int = 0, short: bool = False
) -> str:
    """Return a human-readable representation of a time delta.

    @param time1: Relative time value.
    @param time2: Time base (C{None} for now; 0 for a duration in C{time1}).
    @param precision: How many time units to return (0 = all).
    @param short: Use abbreviations, and right-justify the result to always the same length.
    @return: Formatted duration.
    """
    if time2 is None:
        time2 = time.time()

    duration = (time1 or 0) - time2
    direction = (
        " ago" if duration < 0 else ("+now" if short else " from now") if time2 else ""
    )
    duration = abs(duration)
    parts = [
        ("weeks", duration // (7 * 86400)),
        ("days", duration // 86400 % 7),
        ("hours", duration // 3600 % 24),
        ("mins", duration // 60 % 60),
        ("secs", duration % 60),
    ]

    # Kill leading zero parts
    while len(parts) > 1 and parts[0][1] == 0:
        parts = parts[1:]

    # Limit to # of parts given by precision
    if precision:
        parts = parts[:precision]

    numfmt = ("%d", "%d"), ("%4d", "%2d")
    fmt = "%1.1s" if short else " %s"
    sep = " " if short else ", "
    result = (
        sep.join(
            (numfmt[bool(short)][bool(idx)] + fmt)
            % (val, key[:-1] if val == 1 else key)
            for idx, (key, val) in enumerate(parts)
            if val  # or (short and precision)
        )
        + direction
    )

    if not time1:
        result = "never" if time2 else "N/A"

    if precision and short:
        return result.rjust(1 + precision * 4 + (4 if time2 else 0))
    return result


def convert_strings_in_iter(obj):
    """Helper function to nicely format results"""
    if isinstance(obj, bytes):
        obj = obj.decode()
    elif isinstance(obj, dict):
        for k, v in obj.items():
            obj[convert_strings_in_iter(k)] = convert_strings_in_iter(v)
    elif isinstance(obj, list):
        for k, v in enumerate(obj):
            obj[k] = convert_strings_in_iter(v)
    return obj


def rpc_result_to_string(result) -> str:
    """Helper function to nicely format results"""
    result = convert_strings_in_iter(result)

    if isinstance(result, str):
        return result
    if isinstance(result, bytes):
        return result.decode()
    if hasattr(result, "__iter__"):
        return "\n".join(
            i if isinstance(i, str) else pformat(i, width=240) for i in result
        )
    return repr(result)
