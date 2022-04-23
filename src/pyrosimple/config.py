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

import functools
import logging
import urllib

from pathlib import Path
from typing import Any, Dict

from dynaconf import Dynaconf, Validator

from pyrosimple import error
from pyrosimple.util.parts import Bunch


settings = Dynaconf(
    settings_files=[Path("~/.config/pyrosimple/config.toml").expanduser()],
    envvar="PYRO_CONF",
    envvar_prefix="PYRO",
    validators=[
        Validator("RTORRENT_RC", default="~/.rtorrent.rc"),
        Validator("CONFIG_PY", default="~/.config/pyrosimple/config.py"),
        Validator("SORT_FIELDS", default="name,alias"),
        Validator(
            "CONFIG_VALIDATOR_CALLBACKS",
            default="pyrosimple.torrent.engine:TorrentProxy.add_custom_fields",
        ),
        Validator("ENGINE", default="pyrocore.torrent.rtorrent:RtorrentEngine"),
        Validator("FAST_QUERY", gte=0, lte=2, default=0),
        Validator("SCGI_URL", default=""),
        # TOML sections
        Validator("ALIASES", default={}),
        Validator("CONNECTIONS", default={}),
    ],
)


def autoload_scgi_url() -> str:
    """Load and return SCGI URL, auto-resolving it if necessary"""
    if settings.SCGI_URL:
        return str(settings.SCGI_URL)
    log = logging.getLogger(__name__)
    # Get and check config file name
    rcfile = Path(settings.RTORRENT_RC).expanduser()
    if not rcfile.exists():
        raise error.UserError("Config file %r doesn't exist!" % (rcfile,))

    # Parse the file
    log.debug("Loading rtorrent config from '%s'", rcfile)
    scgi_local: str = ""
    scgi_port: str = ""
    with open(rcfile, "r", encoding="utf-8") as handle:
        continued = False
        for line in handle.readlines():
            # Skip comments, continuations, and empty lines
            line = line.strip()
            continued, was_continued = line.endswith("\\"), continued
            if not line or was_continued or line.startswith("#"):
                continue

            # Be lenient about errors, after all it's not our own config file
            try:
                key, val = line.split("=", 1)
            except ValueError:
                log.debug("Ignored invalid line %r in %r!", line, rcfile)
                continue
            key, val = key.strip(), val.strip()

            # Copy values we're interested in
            if key in ["network.scgi.open_port", "scgi_port"]:
                log.debug("rtorrent.rc: %s = %s", key, val)
                scgi_port = val
            if key in ["network.scgi.open_local", "scgi_local"]:
                log.debug("rtorrent.rc: %s = %s", key, val)
                scgi_local = val

    # Validate fields
    if scgi_local and not scgi_port.startswith("scgi+unix://"):
        scgi_local = "scgi+unix://" + str(Path(scgi_local).expanduser())
    if scgi_port and not scgi_port.startswith("scgi://"):
        scgi_port = "scgi://" + scgi_port

    # Prefer UNIX domain sockets over TCP socketsj
    settings.set("SCGI_URL", scgi_local or scgi_port)

    return str(settings.SCGI_URL)


def lookup_announce_alias(name):
    """Get canonical alias name and announce URL list for the given alias."""
    for alias, urls in settings["ALIASES"].items():
        if alias.lower() == name.lower():
            return alias, urls

    raise KeyError("Unknown alias %s" % (name,))


@functools.cache
def map_announce2alias(url: str) -> str:
    """Get tracker alias for announce URL, and if none is defined, the 2nd level domain."""
    if url in settings["ALIASES"].items():
        return url
    # Try to find an exact alias URL match and return its label
    for alias, urls in settings["ALIASES"].items():
        if any(i == url for i in urls):
            return str(alias)

    # Try to find an alias URL prefix and return its label
    parts = urllib.parse.urlparse(url)
    server = urllib.parse.urlunparse(
        (parts.scheme, parts.netloc, "/", None, None, None)
    )

    for alias, urls in settings["ALIASES"].items():
        if any(i.startswith(server) for i in urls):
            return str(alias)

    # Return 2nd level domain name if no alias found
    try:
        # Try to find based on domain
        domain = ".".join(parts.netloc.split(":")[0].split(".")[-2:])
        for alias, urls in settings["ALIASES"].items():
            if any(i == domain for i in urls):
                return str(alias)
        return domain
    except IndexError:
        return parts.netloc


py_loaded = False


def load_custom_py():
    """Load custom python configuration.

    This only gets called when CLI tools are called to prevent some weird code injection"""
    if py_loaded:
        return
    log = logging.getLogger(__name__)
    config_file = Path(settings.CONFIG_PY).expanduser()
    if config_file.exists():
        log.debug("Loading '%s'...", config_file)
        with open(config_file, "rb") as handle:
            # pylint: disable=exec-used
            exec(handle.read())
    else:
        log.debug("Configuration file '%s' not found!", config_file)


# Remember predefined names
_PREDEFINED = tuple(_ for _ in globals() if not _.startswith("_"))

# Set some defaults to shut up pydev / pylint;
# these later get overwritten by loading the config
custom_template_helpers = Bunch()
traits_by_alias: Dict[Any, Any] = {}
torque: Dict[Any, Any] = {}
