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
        (
            """
        method.insert = cfg.basedir, private|const|string, (cat,"/data/rtorrent/")
        method.insert = cfg.rundir, private|const|string, (cat,"/var/run/rtorrent/")
        network.scgi.open_local = (cat, (cfg.rundir), "scgi.socket")
        """,
            "scgi+unix:///var/run/rtorrent/scgi.socket",
        ),
    ],
)
def test_rtorrentrc_parse(lines, want, tmpdir):
    rc = tmpdir.join("rtorrrent.rc")
    rc.write(lines)
    assert config.scgi_url_from_rtorrentrc(rc) == want


@pytest.mark.parametrize(
    ("url", "aliases", "want"),
    [
        ("http://example.com/announce.php", {}, "example.com"),
        ("http://example.com/announce.php", {"EX": ["example.com"]}, "EX"),
        (
            "http://example.com/announce.php",
            {"EX": ["http://example.com/xxxxx/announce"]},
            "EX",
        ),
        (
            "http://example.com/announce.php",
            {"EX": [" http://example.com/xxxxx/announce"]},
            "EX",
        ),
        (
            "https://example.com/announce.php",
            {"EX": [" https://example.com/xxxxx/announce"]},
            "EX",
        ),
        (
            "https://example.com/announce.php",
            {"EX": ["https://example.com/xxxxx/announce "]},
            "EX",
        ),
    ],
)
def test_aliases(url, aliases, want):
    config.settings["ALIASES"] = aliases
    assert config.map_announce2alias.__wrapped__(url) == want
