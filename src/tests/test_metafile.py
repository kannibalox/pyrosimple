# pylint: disable=
""" Metafile tests.

    Copyright (c) 2009 The PyroScope Project <pyroscope.project@gmail.com>
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


def get_from_dict(data_dict, map_list):
    return reduce(operator.getitem, map_list, data_dict)


def set_in_dict(data_dict, map_list, value):
    get_from_dict(data_dict, map_list[:-1])[map_list[-1]] = value


@pytest.mark.parametrize(
    "announce_url",
    [
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
    ],
)
def test_urls(announce_url):
    mapping = {
        "D": lambda: random.choice("0123456789"),
        "Z": lambda: random.choice(
            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYabcdefghijklmnopqrstuvwxyz"
        ),
    }

    expected = announce_url.replace("D", "*").replace("Z", "*")
    randomized = "".join(mapping.get(i, lambda: i)() for i in announce_url)
    assert expected != randomized
    assert expected == mask_keys(randomized)


@pytest.mark.parametrize(
    "data",
    [
        ["a"],
        {"agsdg": "asdga"},
        {"announce": 3},
    ],
)
def test_bad_dicts(data):
    with pytest.raises(ValueError):
        Metafile(data).check_meta()


@pytest.fixture
def good_metafile():
    return Metafile.from_file(Path(Path(__file__).parent, "multi.torrent"))


@pytest.fixture
def good_metafile_from_path():
    return Metafile.from_path(
        Path(Path(__file__).parent, "data/"), "http://example.com"
    )


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
def test_bad_metadicts(good_metafile, key, data):
    meta = copy.deepcopy(good_metafile)
    set_in_dict(meta, ["info"] + key, data)
    with pytest.raises(ValueError):
        meta.check_meta()


@pytest.mark.parametrize(
    ("key", "data"),
    [
        (["test"], ["a"]),
        (["encoding_std"], "ascii"),
        (["info", "padding"], 5),
    ],
)
def test_clean_bad_metadicts(good_metafile, key, data):
    meta = copy.deepcopy(good_metafile)
    set_in_dict(meta, key, data)
    meta.clean_meta(including_info=True)
    meta.check_meta()
    with pytest.raises(KeyError):
        get_from_dict(meta, key)


# Test various functions holistically


def test_metafile_listing(good_metafile):
    good_metafile.listing()


def test_metafile_size(good_metafile):
    good_metafile.data_size()


@pytest.mark.parametrize(
    ("key", "expected_path", "data"),
    [
        ("test=a", ["test"], "a"),
        ("info.padding=5", ["info", "padding"], "5"),
        ("info.padding=+5", ["info", "padding"], 5),
        ('info["padding"]=+5', ["info", "padding"], 5),
    ],
)
def test_metafile_assign(good_metafile, key, expected_path, data):
    meta = copy.deepcopy(good_metafile)
    meta.assign_fields([key])
    assert get_from_dict(meta, expected_path) == data


def test_metafile_from_path(good_metafile_from_path):
    meta = copy.deepcopy(good_metafile_from_path)
    meta.check_meta()
    assert len(meta.clean_meta(including_info=True)) == 0
    assert meta.hash_check(Path(Path(__file__).parent, "data"))
    assert meta.add_fast_resume(Path(Path(__file__).parent, "data")) == None


def test_metafile_from_filepath():
    filepath = Path(Path(__file__).parent, "data", "file.txt")
    meta = Metafile.from_path(filepath, "http://example.com")
    assert len(meta.clean_meta(including_info=True)) == 0
    assert meta.hash_check(filepath)
    assert meta.add_fast_resume(filepath) == None


def test_metafile_fast_resume():
    single_metafile = Path(Path(__file__).parent, "single.torrent")
    multi_metafile = Path(Path(__file__).parent, "multi.torrent")
    meta = Metafile.from_file(single_metafile)
    assert (
        meta.add_fast_resume(Path(single_metafile.parent, "data", "file.txt")) == None
    )
    assert meta.add_fast_resume(Path(single_metafile.parent, "data")) == None
    assert meta.add_fast_resume(Path(multi_metafile.parent, "data")) == None


def test_metafile_hash_check():
    single_metafile = Path(Path(__file__).parent, "single.torrent")
    multi_metafile = Path(Path(__file__).parent, "multi.torrent")
    meta = Metafile.from_file(single_metafile)
    assert meta.hash_check(Path(single_metafile.parent, "data", "file.txt"))
    assert meta.hash_check(Path(single_metafile.parent, "data"))
    assert meta.hash_check(Path(multi_metafile.parent, "data"))


if __name__ == "__main__":
    unittest.main()
