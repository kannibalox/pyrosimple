""" Configuration.

    For details, see https://pyrosimple.readthedocs.io/en/latest/setup.html

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import functools
import logging
import urllib

from pathlib import Path
from typing import Iterator, Optional, Union

from dynaconf import Dynaconf, Validator

from pyrosimple import error


settings = Dynaconf(
    settings_files=[Path("~/.config/pyrosimple/config.toml").expanduser()],
    envvar="PYRO_CONF",
    envvar_prefix="PYRO",
    validators=[
        # Top-level settings
        Validator("RTORRENT_RC", default="~/.rtorrent.rc"),
        Validator("CONFIG_PY", default="~/.config/pyrosimple/config.py"),
        Validator("SORT_FIELDS", default="name,hash"),
        Validator("FAST_QUERY", gte=0, lte=2, default=0),
        Validator("ITEM_CACHE_EXPIRATION", default=5.0),
        Validator("SAFETY_CHECKS_ENABLED", default=True),
        Validator(
            "MKTOR_IGNORE",
            default=[
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
        ),
        Validator("SCGI_URL", default=""),
        # TOML sections
        Validator("ALIASES", default={}),
        Validator("ALIAS_TRAITS", default={}),
        Validator("CONNECTIONS", default={}),
        # Allow individual overrides in FORMATS section
        Validator(
            "FORMATS__default",
            default='{{d.name}} \t[{{d.alias}}]\n  {{d.is_private|fmt("is_private")}} {{d.is_open|fmt("is_open")}} {{d.is_active|fmt("is_active")}} P{{d.prio}} {%if d.is_complete %}     done{%else%}{{"%8.2f"|format(d.done)}}%{%endif%}\t{{d.size|sz}} U:{{d.up|sz}}/s  D:{{d.down|sz}}/s T:{{d.throttle|fmt("throttle")}}',
        ),
        Validator(
            "FORMATS__short",
            default='{%set ESC = "\x1B" %}{%if d.down > 0%}{{ESC+"[1m"}}{%endif%}{%if d.is_open%}O{%else%} {%endif%}{%if  d.is_active%}A{%else%} {%endif%}{%if not d.is_complete%}{{ESC+"[36m"}}{{ "{:>3}".format(d.done | round | int) }}{{ESC+"[0m"}}{%else%}  D{%endif%} {{"{:>10}".format(d.size | filesizeformat(True))}} {%if d.message%}{{ESC+"[31m"}}{%endif%} {{d.alias.rjust(3)}}{{ESC+"[0m"}} {%if d.down > 0%}{{ESC+"[1m"}}{%endif%}{{d.name}}{{ESC+"[0m"}}',
        ),
        Validator(
            "FORMATS__filelist",
            default="{% for f in d.files %}{{d.realpath}}{% if d.is_multi_file %}/{{f.path}}{% endif %}{% if loop.index != loop.length %}\n{% endif %}{% endfor %}",
        ),
        Validator(
            "FORMATS__action",
            default="{{now()|iso}} {{action}}\t {{d.name}} [{{d.alias}}]",
        ),
    ],
)


def scgi_url_from_rtorrentrc(rcfile: Union[str, Path]) -> Optional[str]:
    """Parse a rtorrent.rc file and"""
    log = logging.getLogger(__name__)
    log.debug("Loading rtorrent config from '%s'", rcfile)
    scgi_local: str = ""
    scgi_port: str = ""
    rcfile = Path(rcfile)
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

    settings.set("SCGI_URL", scgi_url)

    return str(settings.SCGI_URL)


def lookup_announce_alias(name: str):
    """Get canonical alias name and announce URL list for the given alias."""
    for alias, urls in settings["ALIASES"].items():
        if alias.lower() == name.lower():
            return alias, urls

    raise KeyError(f"Unknown alias {name}")


def lookup_announce_url(name: str):
    """Get canonical alias name and announce URL list for the given alias.

    Unlike lookup_announce_alias, only valid URLs are returned"""
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


def lookup_connection_alias(url: str) -> str:
    """Convert a connection alias to the actual URL (if set in the config"""
    if url in settings["CONNECTIONS"]:
        return str(settings["CONNECTIONS"][url])
    return url


def multi_connection_lookup(url: str) -> Iterator[str]:
    """Return a list of urls.

    This is separate from lookup_connection_alias due to scripts needing to be written specifically
    to handle this"""
    val = settings["CONNECTIONS"].get(url, [url])
    if isinstance(val, list):
        for v in val:
            yield lookup_connection_alias(v)
    else:
        yield lookup_connection_alias(val)
