# pylint: disable=
""" Torrent Engine tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
import logging
import unittest

import pytest

from pyrosimple.torrent import engine, rtorrent


log = logging.getLogger(__name__)
log.debug("module loaded")


class IntervalTest(unittest.TestCase):
    INTERVAL_DATA = [
        ("R1377390013R1377390082", dict(end=1377390084), 2),
        ("R1353618135P1353618151", dict(start=1353618141), 10),
    ]

    def test_interval_sum(self):
        for interval, kwargs, expected in self.INTERVAL_DATA:
            result = engine._interval_sum(interval, **kwargs)
            assert expected == result, f"for interval={interval!r} kw={kwargs!r}"


EXAMPLE_HASH = "BAE3666F5C14AEC4BF6DE49C752E3D148216B0DE"


# Very basic field testing
@pytest.mark.parametrize(
    ("field", "data", "expected"),
    [
        ("hash", {}, EXAMPLE_HASH),
        ("completed", {"d.custom=tm_completed": ""}, 0),
        ("completed", {"d.custom=tm_completed": "10"}, 10),
        ("done", {"d.completed_bytes": 12, "d.size_bytes": 144}, (12 / 144) * 100),
        ("is_open", {"d.is_open": 1}, True),
        ("xfer", {"d.up.rate": 5, "d.down.rate": 7}, 12),
    ],
)
def test_fields(field, data, expected):
    test_data = {
        "d.hash": EXAMPLE_HASH,
    }.copy()
    test_data.update(data)
    item = rtorrent.RtorrentItem(
        None,
        {hash: EXAMPLE_HASH},
        test_data,
        cache_expires=0,
    )
    assert getattr(item, field) == expected


if __name__ == "__main__":
    unittest.main()
