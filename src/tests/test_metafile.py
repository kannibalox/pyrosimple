# -*- coding: utf-8 -*-
# pylint: disable=
""" Metafile tests.

    Copyright (c) 2009 The PyroScope Project <pyroscope.project@gmail.com>

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

import copy
import operator
import random
import unittest

from functools import reduce  # forward compatibility for Python 3
from pathlib import Path

import bencode
import pytest

from pyrosimple.util.metafile import *  # @UnusedWildImport


# helper methods to make tests easier to write
def get_from_dict(data_dict, map_list):
    return reduce(operator.getitem, map_list, data_dict)


def set_in_dict(data_dict, map_list, value):
    get_from_dict(data_dict, map_list[:-1])[map_list[-1]] = value


class MaskTest(unittest.TestCase):
    def test_urls(self):
        testcases = (
            "http://example.com:1234/user/ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ/announce",
            "http://example.com/announce.php?passkey=ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ",
            "http://example.com/announce.php?passkey=ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ&someparam=0",
            "http://example.com/DDDDD/ZZZZZZZZZZZZZZZZ/announce",
            "http://example.com/tracker.php/ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ/announce",
            "https://example.com/announce.php?passkey=ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ",
            "http://tracker1.example.com/TrackerServlet/ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ/DDDDDDD/announce",
            "http://example.com:12345/ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ/announce",
            "http://example.com/announce.php?pid=ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ",
            "http://example.com:1234/a/ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ/announce",
            "http://example.com/announce.php?passkey=ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ&uid=DDDDD",
        )
        mapping = {
            "D": lambda: random.choice("0123456789"),
            "Z": lambda: random.choice(
                "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYabcdefghijklmnopqrstuvwxyz"
            ),
        }

        for testcase in testcases:
            expected = testcase.replace("D", "*").replace("Z", "*")
            randomized = "".join(mapping.get(i, lambda: i)() for i in testcase)
            assert expected != randomized
            assert expected == mask_keys(randomized)


@pytest.fixture
def good_metainfo():
    with Path(Path(__file__).parent, "multi.torrent").open("rb") as fh:
        return bencode.decode(fh.read())


@pytest.mark.parametrize(
    "data",
    [
        ["a"],
        {"agsdg": "asdga"},
        {"announce", 3},
    ],
)
def test_bad_dicts(data):
    with pytest.raises(ValueError):
        check_meta(data)


@pytest.mark.parametrize(
    ("key", "data"),
    [
        ([], ["a"]),
        (["pieces"], "test"),
        (["piece length"], -1),
        (["name"], 5),
        (["name"], "/tmp/file"),
        (["length"], [{"length": 1, "path": "test"}]),
        (["length"], -1),
        (["files"], 1),
        (["files"], [1]),
        (["files"], [{"length": -1}]),
        (["files"], [{"length": 1, "path": -1}]),
        (["files"], [{"length": 1, "path": -1}]),
        (["files"], [{"length": 1, "path": [-1]}]),
        (["files"], [{"length": 1, "path": ["file", "/tmp/file"]}]),
        (["files"], [{"length": 1, "path": ["..", "file"]}]),
        (
            ["files"],
            [
                {"length": 1, "path": ["file"]},
                {"length": 1, "path": ["file"]},
            ],
        ),
    ],
)
def test_bad_metadicts(good_metainfo, key, data):
    meta = copy.deepcopy(good_metainfo)
    set_in_dict(meta, ["info"] + key, data)
    with pytest.raises(ValueError):
        check_meta(meta)


def test_metafile_listing(good_metainfo):
    meta = Metafile(Path(Path(__file__).parent, "multi.torrent"))
    meta.listing()


if __name__ == "__main__":
    unittest.main()
