""" Python Torrent Tools Core Package.

    Copyright (c) 2010 The PyroScope Project <pyroscope.project@gmail.com>
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

from pyrosimple.torrent import rtorrent


def connect(uri=None):
    """Initialize everything for interactive use.

    Returns a ready-to-use RtorrentEngine object.
    """
    return rtorrent.RtorrentEngine(uri)


def view(
    viewname="default",
    matcher=None,
):
    """Helper for interactive / high-level API use."""
    return connect().view(viewname, matcher)
