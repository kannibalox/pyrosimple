# pylint: disable=
""" RTorrent tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
import pytest
import unittest

import pyrosimple
from pyrosimple import error
from pyrosimple.torrent import rtorrent
from pyrosimple.util.rpc import RTorrentProxy
from pyrosimple.util.parts import Bunch


@pytest.mark.parametrize(
    ("template", "fields"),
    [
        ("{{d.size}}", ["size"]),
        (
            "{{d.name|center}}{% if d.is_multi_file %}{{d.size}}{% endif %}",
            ["name", "size", "is_multi_file"],
        ),
    ],
)
def test_fields_from_template(template, fields):
    assert sorted(list(rtorrent.get_fields_from_template(template))) == sorted(fields)


def test_validate_sort():
    assert rtorrent.validate_field_list("name,size") == ["name", "size"]
    assert rtorrent.validate_field_list("name.center,size.raw", True) == [
        "name",
        "size",
    ]
    with pytest.raises(error.UserError):
        rtorrent.validate_sort_fields("very_fake_field.raw")
    with pytest.raises(error.UserError):
        rtorrent.validate_sort_fields("name.very_fake_filter")


def test_validate_sort():
    rtorrent.validate_sort_fields("name,size")
    rtorrent.validate_sort_fields("name,-size")
    with pytest.raises(error.UserError):
        rtorrent.validate_sort_fields("very_fake_field")


class MockProxy:
    def log(self, *_):
        pass

    def d_multicall2(self, _, _viewname, *fields):
        print(_viewname)
        print(fields)
        ret_items = []
        for f in fields:
            ret_items.append([i[f] for i in self.items])
        return ret_items

    def d_name(self, hash):
        for i in items:
            if i["d.hash="] == hash:
                return i["d.name="]

    def __init__(self):
        self.d = Bunch(
            multicall2=self.d_multicall2,
            name=self.d_name,
        )
        self.items = [
            {
                "d.name=": "Test.Item",
                "d.hash=": "A" * 40,
            }
        ]


def test_rpc():
    e = pyrosimple.connect("localhost:8080")
    e.rpc = MockProxy()
    e.log("test")
    items = list(e.items("default", ["d.name"]))
