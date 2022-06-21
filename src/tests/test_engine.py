# pylint: disable=
""" Torrent Engine tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
import logging
import unittest

from pyrosimple.torrent import engine


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


class EngineTest(unittest.TestCase):
    def test_engine(self):
        pass


if __name__ == "__main__":
    unittest.main()
