""" Python Torrent Tools Core Package.

    Copyright (c) 2010 The PyroScope Project <pyroscope.project@gmail.com>
"""


from pyrosimple.torrent import rtorrent


def connect(url=None):
    """Initialize everything for interactive use.

    Returns a ready-to-use RtorrentEngine object.
    """
    return rtorrent.RtorrentEngine(url)


def view(
    viewname="default",
    matcher=None,
):
    """Helper for interactive / high-level API use."""
    return connect().view(viewname, matcher)
