# -*- coding: utf-8 -*-
""" Configuration.

    For details, see https://pyrosimple.readthedocs.io/en/latest/setup.html

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
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

import urllib

from pathlib import Path
from typing import Any, Dict, List
import functools

from dynaconf import Dynaconf, Validator

from pyrosimple.util.parts import Bunch
from pyrosimple.util import pymagic


settings = Dynaconf(
    settings_files=[Path("~/.config/pyrosimple/config.toml").expanduser()],
    envvar="PYRO_CONF",
    envvar_prefix="PYRO",
    validators=[
        Validator("RTORRENT_RC", default="~/.rtorrent.rc"),
        Validator("CONFIG_PY", default=Path("~/.config/pyrosimple/config.py").expanduser()),
        Validator("SORT_FIELDS", default="name,alias"),
        Validator("CONFIG_VALIDATOR_CALLBACKS", default="pyrosimple.torrent.engine:TorrentProxy.add_custom_fields"),
        Validator("ENGINE", default="pyrocore.torrent.rtorrent:RtorrentEngine"),
        Validator("FAST_QUERY", gte=0, lte=2, default=0),
        Validator("ALIASES", default={}),
        Validator("SCGI_URL", default=""),
    ]
)

def lookup_announce_alias(name):
    """Get canonical alias name and announce URL list for the given alias."""
    for alias, urls in settings['ALIASES'].items():
        if alias.lower() == name.lower():
            return alias, urls

    raise KeyError("Unknown alias %s" % (name,))


@functools.cache
def map_announce2alias(url):
    """Get tracker alias for announce URL, and if none is defined, the 2nd level domain."""

    # Try to find an exact alias URL match and return its label
    for alias, urls in settings['ALIASES'].items():
        if any(i == url for i in urls):
            return alias

    # Try to find an alias URL prefix and return its label
    parts = urllib.parse.urlparse(url)
    server = urllib.parse.urlunparse(
        (parts.scheme, parts.netloc, "/", None, None, None)
    )

    for alias, urls in settings['ALIASES'].items():
        if any(i.startswith(server) for i in urls):
            return alias

    # Try to find based on domain
    domain = '.'.join(parts.netloc.split(':')[0].split('.')[-2:])
    for alias, urls in settings['ALIASES'].items():
        if any(i == domain for i in urls):
            return alias

    # Return 2nd level domain name if no alias found
    try:
        return ".".join(parts.netloc.split(":")[0].split(".")[-2:])
    except IndexError:
        return parts.netloc

# Remember predefined names
_PREDEFINED = tuple(_ for _ in globals() if not _.startswith("_"))

# Set some defaults to shut up pydev / pylint;
# these later get overwritten by loading the config
scgi_url = ""
engine = Bunch(open=lambda: None)
formats: Dict[Any, Any] = {}
config_validator_callbacks: List[Any] = []
custom_field_factories: List[Any] = []
custom_template_helpers = Bunch()
waif_pattern_list: List[Any] = []
traits_by_alias: Dict[Any, Any] = {}
connections: List[str] = []
torque: Dict[Any, Any] = {}
