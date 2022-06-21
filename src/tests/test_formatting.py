# pylint: disable=
""" Item Formatting tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
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
        (5 * (1024**4), "5.0 TiB".rjust(10)),
        (5 * (1024**7), "5242880.0 PiB".rjust(10)),
        (-5, "-??? bytes".rjust(10)),
    ],
)
def test_fmt_size(size, expected):
    assert formatting.fmt_sz(size) == expected
