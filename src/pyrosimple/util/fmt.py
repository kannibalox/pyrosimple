# -*- coding: utf-8 -*-
# pylint: disable=invalid-name,no-else-return
""" Data Formatting.

    Copyright (c) 2009, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
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
import codecs
import logging
import datetime
from pprint import pformat

log = logging.getLogger(__name__)


def human_size(size):
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
    for unit in ("KiB", "MiB", "GiB"):
        size /= 1024.0
        if size < 1024:
            return "%6.1f %s" % (size, unit)

    return "%6.1f GiB" % size


def iso_datetime(timestamp=None):
    """Convert UNIX timestamp to ISO datetime string.

    @param timestamp: UNIX epoch value (default: the current time).
    @return: Timestamp formatted as "YYYY-mm-dd HH:MM:SS".
    """
    if timestamp is None:
        timestamp = time.time()
    return datetime.datetime.fromtimestamp(timestamp).isoformat(" ")[:19]


def iso_datetime_optional(timestamp):
    """Convert UNIX timestamp to ISO datetime string, or "never".

    @param timestamp: UNIX epoch value.
    @return: Timestamp formatted as "YYYY-mm-dd HH:MM:SS", or "never" for false values.
    """
    if timestamp:
        return iso_datetime(timestamp)
    return "never"


def human_duration(time1, time2=None, precision=0, short=False):
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


def to_unicode(text):
    """Return a decoded unicode string.
    False values are returned untouched.
    """
    if not text or isinstance(text, str):
        return text

    try:
        # Try UTF-8 first
        return text.decode("UTF-8")
    except UnicodeError:
        try:
            # Then Windows Latin-1
            return text.decode("CP1252")
        except UnicodeError:
            # Give up, return byte string in the hope things work out
            return text


def to_utf8(text):
    """Enforce UTF8 encoding."""
    # return empty/false stuff unaltered
    if not text:
        if isinstance(text, str):
            text = b""
        return text

    try:
        # Is it a unicode string, or pure ascii?
        return text.encode("utf8")
    except (UnicodeDecodeError, AttributeError):
        try:
            # Is it a utf8 byte string?
            if text.startswith(codecs.BOM_UTF8):
                text = text[len(codecs.BOM_UTF8) :]
            return text.decode("utf8").encode("utf8")
        except UnicodeDecodeError:
            # Check BOM
            if text.startswith(codecs.BOM_UTF16_LE):
                encoding = "utf-16le"
                text = text[len(codecs.BOM_UTF16_LE) :]
            elif text.startswith(codecs.BOM_UTF16_BE):
                encoding = "utf-16be"
                text = text[len(codecs.BOM_UTF16_BE) :]
            else:
                # Assume CP-1252
                encoding = "cp1252"

            try:
                return text.decode(encoding).encode("utf8")
            except UnicodeDecodeError as exc:
                for line in text.splitlines():
                    try:
                        line.decode(encoding).encode("utf8")
                    except UnicodeDecodeError:
                        log.warn(
                            "Cannot transcode the following into UTF8 cause of %s: %r"
                            % (exc, line)
                        )
                        break
                return text  # Use as-is and hope the best


def to_console(text):
    """Return a byte string intended for console output."""
    if isinstance(text, bytes):
        # For now, leave byte strings as-is (ignoring possible display problems)
        return text

    # Convert other stuff into an UTF-8 string
    return str(text).encode("utf8")


def convert_strings_in_iter(obj):
    # Unicode will get pformatted with a 'u' prefix on 2
    if False and isinstance(obj, unicode):
        obj = obj.encode("utf8")
    # Bytes will get pformatted with a 'b' prefix on 3
    elif not False and isinstance(obj, bytes):
        obj = obj.decode()
    elif isinstance(obj, dict):
        for k, v in obj.items():
            obj[convert_strings_in_iter(k)] = convert_strings_in_iter(v)
    elif isinstance(obj, list):
        for k, v in enumerate(obj):
            obj[k] = convert_strings_in_iter(v)
    return obj


def xmlrpc_result_to_string(result, pretty=False):
    result = convert_strings_in_iter(result)

    if pretty:
        # Pretty-print if requested, or it's a collection and not a scalar
        return pformat(result)
    elif isinstance(result, str) or isinstance(result, bytes):
        return to_unicode(result)
    elif hasattr(result, "__iter__"):
        return "\n".join(i if isinstance(i, str) else pformat(i) for i in result)
    else:
        return repr(result)
