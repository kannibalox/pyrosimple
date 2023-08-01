""" Configuration.

    For details, see https://pyrosimple.readthedocs.io/en/latest/setup.html

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""

import functools
import logging
import os
import re
import shlex
import urllib

from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple, Union


try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

from box.box import Box

from pyrosimple import error


ENVVAR = "PYRO_CONF"
ENVVAR_PREFIX = "PYRO"
SETTINGS_FILE = Path("~/.config/pyrosimple/config.toml").expanduser()

DEFAULT_SETTINGS = Box(
    {
        "SCGI_URL": "",
        "RTORRENT_RC": "~/.rtorrent.rc",
        "CONFIG_PY": "~/.config/pyrosimple/config.py",
        "CONFIG_PY_LOADED": False,
        "SORT_FIELDS": "name,hash",
        "FAST_QUERY": 0,
        "ITEM_CACHE_EXPIRATION": 5.0,
        "SAFETY_CHECKS_ENABLED": True,
        "MKTOR_IGNORE": [
            "core",
            "CVS",
            ".*",
            "*~",
            "*.swp",
            "*.tmp",
            "*.bak",
            "[Tt]humbs.db",
            "[Dd]esktop.ini",
            "ehthumbs_vista.db",
        ],
        # TOML sections
        "ALIASES": {},
        "ALIAS_TRAITS": {},
        "CONNECTIONS": {},
        "TORQUE": Box({"_settings": Box()}),
        # Allow individual overrides in FORMATS section
        "FORMATS": {
            "default": '{{d.name}} \t[{{d.alias}}]\n  {{d.is_private|fmt("is_private")}} {{d.is_open|fmt("is_open")}} {{d.is_active|fmt("is_active")}} P{{d.prio|int}} {%if d.is_complete %}     done{%else%}{{"%8.2f"|format(d.done)}}%{%endif%}\t{{d.size|sz}} U:{{d.up|sz}}/s  D:{{d.down|sz}}/s T:{{d.throttle|fmt("throttle")}}',
            "short": '{%set ESC = "\x1B" %}{%if d.down > 0%}{{ESC+"[1m"}}{%endif%}{%if d.is_open%}O{%else%} {%endif%}{%if  d.is_active%}A{%else%} {%endif%}{%if not d.is_complete%}{{ESC+"[36m"}}{{ "{:>3}".format(d.done | round | int) }}{{ESC+"[0m"}}{%else%}  D{%endif%} {{"{:>10}".format(d.size | filesizeformat(True))}} {%if d.message%}{{ESC+"[31m"}}{%endif%} {{d.alias.rjust(3)}}{{ESC+"[0m"}} {%if d.down > 0%}{{ESC+"[1m"}}{%endif%}{{d.name}}{{ESC+"[0m"}}',
            "filelist": "{% for f in d.files %}{{d.realpath}}{% if d.is_multi_file %}/{{f.path}}{% endif %}{% if loop.index != loop.length %}\n{% endif %}{% endfor %}",
            "action": "{{now()|iso}} {{action}}\t {{d.name}} [{{d.alias}}]",
        },
    }
)


def load_settings() -> Box:
    """Load settings from (in order of precedence): the defaults, a
    TOML config file, environment variables
    """
    settings_box: Box = DEFAULT_SETTINGS.copy()
    settings_file = Path(os.getenv(ENVVAR, str(SETTINGS_FILE))).expanduser()
    if settings_file.exists():
        settings_file_box = Box(
            {
                k.upper(): v
                for k, v in tomllib.loads(settings_file.read_text("utf-8")).items()
            }
        )
        settings_box.merge_update(settings_file_box)
    env_settings = {}
    for k, v in os.environ.items():
        if k.startswith(f"{ENVVAR_PREFIX}_"):
            key = k[len(ENVVAR_PREFIX) + 1 :]
            env_settings[key] = v
    settings_box.merge_update(Box(env_settings))
    return settings_box


settings: Box = load_settings()


class RCLexer(shlex.shlex):
    """Helper to split argument lists."""

    def __init__(self, text: str):
        super().__init__(text)
        self.whitespace += ","
        self.whitespace_split = True
        self.commenters = ""


def expand_rc(rcfile: Path) -> List[Tuple[str, str]]:
    """Return key/val pairs for each line in the rc file, with some
    very naive string replacement for cat= calls"""
    log = logging.getLogger(__name__)
    data: List[Tuple[str, str]] = []
    replacements: Dict[str, str] = {}
    with rcfile.open("r", encoding="utf-8") as handle:
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
            priv_string_match = re.match(
                r"([.\w]+),\s*private\|const\|string,\s*\(cat,(.*)\)", val
            )
            if priv_string_match:
                str_result = ""
                for arg in RCLexer(priv_string_match.group(2)):
                    if arg.startswith("("):
                        str_result += replacements.get(arg[1:-1], "")
                    if arg.startswith('"'):
                        str_result += arg[1:-1]
                val = str_result
                replacements[priv_string_match.group(1)] = str_result
            if key in [
                "network.scgi.open_local",
                "scgi_local",
                "scgi_port",
                "network.scgi.open_port",
            ]:
                simple_cat_match = re.match(r"\(cat,(.*)\)", val)
                if simple_cat_match:
                    str_result = ""
                    for arg in RCLexer(simple_cat_match.group(1)):
                        if arg.startswith("("):
                            str_result += replacements.get(arg[1:-1], "")
                        if arg.startswith('"'):
                            str_result += arg[1:-1]
                    val = str_result
            data.append((key, val))
        return data


def scgi_url_from_rtorrentrc(rcfile: Union[str, Path]) -> Optional[str]:
    """Parse a rtorrent.rc file and"""
    log = logging.getLogger(__name__)
    log.debug("Loading rtorrent config from '%s'", rcfile)
    scgi_local: str = ""
    scgi_port: str = ""
    rcfile = Path(rcfile)
    for key, val in expand_rc(rcfile):
        # Copy values we're interested in
        if key in ["network.scgi.open_port", "scgi_port"]:
            log.debug("rtorrent.rc: %s = %s", key, val)
            scgi_port = val
        if key in ["network.scgi.open_local", "scgi_local"]:
            log.debug("rtorrent.rc: %s = %s", key, val)
            scgi_local = val

    # Validate fields
    if scgi_local and not scgi_local.startswith("scgi+unix://"):
        scgi_local = "scgi+unix://" + str(Path(scgi_local).expanduser())
    if scgi_port and not scgi_port.startswith("scgi://"):
        scgi_port = "scgi://" + scgi_port

    return scgi_local or scgi_port
    # Prefer UNIX domain sockets over TCP sockets


def autoload_scgi_url() -> str:
    """Load and return the SCGI URL, auto-resolving it if necessary."""
    if settings.SCGI_URL:
        return str(settings.SCGI_URL)
    # Get and check config file name
    rcfile = Path(settings.RTORRENT_RC).expanduser()
    if not rcfile.exists():
        raise error.UserError(f"rTorrent RC file '{rcfile}' doesn't exist!")
    scgi_url = scgi_url_from_rtorrentrc(rcfile)

    settings["SCGI_URL"] = scgi_url

    return str(settings.SCGI_URL)


def lookup_announce_alias(name: str):
    """Get canonical alias name and announce URL list for the given
    alias."""
    for alias, urls in settings["ALIASES"].items():
        if alias.lower() == name.lower():
            return alias, urls

    raise KeyError(f"Unknown alias {name}")


def lookup_announce_url(name: str):
    """Get canonical alias name and announce URL list for the given
    alias.

    Unlike lookup_announce_alias, only valid URLs are returned
    """
    for alias, urls in settings["ALIASES"].items():
        if alias.lower() == name.lower():
            result = []
            for url in urls:
                if urllib.parse.urlparse(url).scheme:
                    result.append(url)
            return alias, result

    raise KeyError(f"Unknown alias {name}")


@functools.lru_cache(maxsize=None)
def map_announce2alias(url: str) -> str:
    """Get tracker alias for announce URL, and if none is defined, the
    2nd level domain."""
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


def load_custom_py():
    """Load custom python configuration.

    This only gets called manually to prevent some weird code
    injection if pyrosimple is ever used in a library.
    """
    log = logging.getLogger(__name__)
    if not settings.CONFIG_PY:
        log.debug("Custom code loading is disabled")
    if settings.CONFIG_PY_LOADED:
        log.debug("Custom code has already been loaded")
    config_file = Path(settings.CONFIG_PY).expanduser()
    if config_file.exists():
        log.debug("Loading '%s'...", config_file)
        with open(config_file, "rb") as handle:
            # pylint: disable=exec-used
            exec(handle.read())
        settings.CONFIG_PY_LOADED = True
    else:
        log.debug("Configuration file '%s' not found.", config_file)


def lookup_connection_alias(url: str) -> str:
    """Convert a connection alias to the actual URL (if set in the
    config"""
    if url in settings["CONNECTIONS"]:
        return str(settings["CONNECTIONS"][url])
    return url


def multi_connection_lookup(url: str) -> Iterator[str]:
    """Return a list of urls.

    This is separate from lookup_connection_alias due to scripts
    needing to be written specifically to handle this.
    """
    val = settings["CONNECTIONS"].get(url, [url])
    if isinstance(val, list):
        for v in val:
            yield lookup_connection_alias(v)
    else:
        yield lookup_connection_alias(val)
