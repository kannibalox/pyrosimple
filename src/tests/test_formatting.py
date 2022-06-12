# -*- coding: utf-8 -*-
# pylint: disable=
""" Item Formatting tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""
import pytest

from pyrosimple.torrent import formatting
from pyrosimple.util import fmt


@pytest.mark.parametrize(
    ("size", "expected"),
    [(5 * 1024, "5.0 KiB"), (0, "0 bytes"), (7 * 1024 * 1024 * 1024, "7.0 GiB")],
)
def test_fmt_human_size(size, expected):
    assert fmt.human_size(size) == expected


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (5 * 1024, "5.0 KiB".rjust(10)),
        (0, "0 bytes".rjust(10)),
        ("invalid", "N/A".rjust(10)),
    ],
)
def test_fmt_size(size, expected):
    assert formatting.fmt_sz(size) == expected
