# -*- coding: utf-8 -*-
# pylint: disable=invalid-name,no-else-return
""" Data Formatting.

    Copyright (c) 2009, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
import datetime
import logging

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
import time

from typing import Union, Optional
from pprint import pformat


log = logging.getLogger(__name__)


def human_size(size: int) -> str:
    """Return a human-readable representation of a byte size.

    @param size: Number of bytes as an integer or string.
    @return: String of length 10 with the formatted result.
    """
    if isinstance(size, str):
        size = int(size, 10)

    if size < 0:
        return "-??? bytes"

    if size < 1024:
        return "%4d bytes" % size

    rem = float(size)
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        rem /= 1024.0
        if rem < 1024:
            return "%6.1f %s" % (rem, unit)

    return "%6.1f TiB" % rem


def iso_datetime(timestamp:Optional[float]=None) -> str:
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


def human_duration(time1: float, time2=Optional[float], precision: int=0, short: bool=False) -> str:
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
    else:
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


def xmlrpc_result_to_string(result) -> str:
    """Helper function to nicely format results"""
    result = convert_strings_in_iter(result)

    if isinstance(result, str):
        return result
    elif isinstance(result, bytes):
        return result.decode()
    elif hasattr(result, "__iter__"):
        return "\n".join(i if isinstance(i, str) else pformat(i) for i in result)
    else:
        return repr(result)
