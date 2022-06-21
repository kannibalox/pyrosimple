""" Data Formatting.

    Copyright (c) 2009, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import datetime
import logging
import time

from pprint import pformat
from typing import Optional


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
        return "\n".join(i if isinstance(i, str) else pformat(i) for i in result)
    return repr(result)
