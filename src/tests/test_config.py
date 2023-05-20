# pylint: disable=
""" Configuration tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
import os

import pytest

from pyrosimple import config


@pytest.mark.parametrize(
    ("lines", "want"),
    [
        (
            "network.scgi.open_local = ~/.config/rtorrent/socket",
            "scgi+unix://" + os.path.expanduser("~/.config/rtorrent/socket"),
        ),
        ("scgi_local = /tmp/rtorrent.sock", "scgi+unix:///tmp/rtorrent.sock"),
        ("scgi_local=/tmp/rtorrent.sock", "scgi+unix:///tmp/rtorrent.sock"),
    ],
)
def test_rtorrentrc_parse(lines, want, tmpdir):
    rc = tmpdir.join("rtorrrent.rc")
    rc.write(lines)
    assert config.scgi_url_from_rtorrentrc(rc) == want
