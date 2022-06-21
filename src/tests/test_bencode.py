# pylint: disable=missing-docstring, wildcard-import, unused-wildcard-import
# pylint: disable=protected-access, too-few-public-methods
""" Bencode tests.
    List of test cases taken from original BitTorrent code by Bram Cohen.
    Copyright (c) 2009-2020 The PyroScope Project <pyroscope.project@gmail.com>
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
import unittest

from io import BytesIO

import bencode
import pytest

from bencodepy.exceptions import BencodeDecodeError


@pytest.mark.parametrize(
    "val",
    [
        b"",
        b"i",
        b"di1",
        b"0:0:",
        b"ie",
        b"i341foo382e",
        b"i-0e",
        b"i123",
        b"i6easd",
        b"35208734823ljdahflajhdf",
        b"2:abfdjslhfld",
        b"02:xy",
        b"l",
        b"l0:",
        b"leanfdldjfh",
        b"relwjhrlewjh",
        b"d",
        b"defoobar",
        b"d3:fooe",
        b"di1e0:e",
        # "d1:b0:1:a0:e",
        # "d1:a0:1:a0:e",
        b"i03e",
        "l01:ae",
        b"1",
        b"1:",
        b"9999:x",
        b"l0:",
        b"d0:0:",
        b"d0:",
        b"10:45646",
    ],
)
def test_bencode_decode_errors(val):
    with pytest.raises(BencodeDecodeError):
        bencode.decode(val)


@pytest.mark.parametrize(
    "val, expected",
    [
        (b"i4e", 4),
        (b"i0e", 0),
        (b"i123456789e", 123456789),
        (b"i-10e", -10),
        (b"0:", ""),
        (b"3:abc", "abc"),
        (b"10:1234567890", "1234567890"),
        ("10:1234567890", "1234567890"),
        (b"le", []),
        (b"l0:0:0:e", ["", "", ""]),
        (b"li1ei2ei3ee", [1, 2, 3]),
        (b"l3:asd2:xye", ["asd", "xy"]),
        (b"ll5:Alice3:Bobeli2ei3eee", [["Alice", "Bob"], [2, 3]]),
        (b"de", {}),
        (b"d3:agei25e4:eyes4:bluee", {"age": 25, "eyes": "blue"}),
        (
            b"d8:spam.mp3d6:author5:Alice6:lengthi100000eee",
            {"spam.mp3": {"author": "Alice", "length": 100000}},
        ),
    ],
)
def test_bencode_decode_values(val, expected):
    assert bencode.decode(val) == expected


class DunderBencode:
    def __init__(self, num):
        self.num = num

    def __bencode__(self):
        return f"DunderBencode-{self.num}"


@pytest.mark.parametrize(
    "val",
    [
        #    object,
        #    object(),
        {None: None},
        {object: None},
        {object(): None},
        {DunderBencode(2): "test"},
    ],
)
def test_bencode_errors(val):
    with pytest.raises(TypeError):
        bencode.encode(val)


@pytest.mark.parametrize(
    "val, expected",
    [
        (4, b"i4e"),
        (0, b"i0e"),
        (-10, b"i-10e"),
        (12345678901234567890, b"i12345678901234567890e"),
        (b"", b"0:"),
        (b"abc", b"3:abc"),
        ("abc", b"3:abc"),
        (b"1234567890", b"10:1234567890"),
        ([], b"le"),
        ([1, 2, 3], b"li1ei2ei3ee"),
        ([[b"Alice", b"Bob"], [2, 3]], b"ll5:Alice3:Bobeli2ei3eee"),
        ({}, b"de"),
        ({b"age": 25, b"eyes": b"blue"}, b"d3:agei25e4:eyes4:bluee"),
        ({"age": 25, "eyes": "blue"}, b"d3:agei25e4:eyes4:bluee"),
        (
            {b"spam.mp3": {b"author": b"Alice", b"length": 100000}},
            b"d8:spam.mp3d6:author5:Alice6:lengthi100000eee",
        ),
        ([True, False], b"li1ei0ee"),
    ],
)
def test_bencode_values(val, expected):
    assert bencode.encode(val) == expected


if __name__ == "__main__":
    pytest.main([__file__])
