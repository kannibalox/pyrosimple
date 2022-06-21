""" Torrent Item Formatting and Filter Rule Parsing.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import json
import logging
import os
import re

from pathlib import Path
from typing import Dict, Generator, Union

import jinja2

from jinja2 import Environment, FileSystemLoader, Template

from pyrosimple import error
from pyrosimple.torrent import engine, rtorrent
from pyrosimple.util import fmt, pymagic


def fmt_sz(intval: int) -> str:
    """Format a byte sized value."""
    try:
        return fmt.human_size(intval).rjust(10)
    except (ValueError, TypeError):
        return "N/A".rjust(10)


def fmt_iso(timestamp: float) -> str:
    """Format a UNIX timestamp to an ISO datetime string."""
    try:
        return fmt.iso_datetime(timestamp)
    except (ValueError, TypeError):
        return "N/A".rjust(len(fmt.iso_datetime(0)))


def fmt_duration(duration: int) -> str:
    """Format a duration value in seconds to a readable form."""
    try:
        return fmt.human_duration(float(duration), 0, 2, True)
    except (ValueError, TypeError):
        return "N/A".rjust(len(fmt.human_duration(0, 0, 2, True)))


def fmt_delta(timestamp) -> str:
    """Format a UNIX timestamp to a delta (relative to now)."""
    try:
        return fmt.human_duration(float(timestamp), precision=2, short=True)
    except (ValueError, TypeError):
        return "N/A".rjust(len(fmt.human_duration(0, precision=2, short=True)))


def fmt_pc(floatval: float):
    """Scale a ratio value to percent."""
    return round(float(floatval) * 100.0, 2)


def fmt_strip(val: str) -> str:
    """Strip leading and trailing whitespace."""
    return str(val).strip()


def fmt_subst(val, regex, subst):
    """Replace regex with string."""
    return re.sub(regex, subst, val)


def fmt_mtime(val: str) -> float:
    """Modification time of a path."""
    p = Path(str(val))
    if p.exists():
        return p.stat().st_mtime
    return 0.0


def fmt_pathbase(val: str) -> str:
    """Base name of a path."""
    return os.path.basename(val or "")


def fmt_pathname(val: str) -> str:
    """Base name of a path, without its extension."""
    return os.path.splitext(os.path.basename(val or ""))[0]


def fmt_raw(val):
    """A little magic to allow showing the raw value of a field in rtcontrol"""
    return val


def fmt_fmt(val, field):
    """Apply a field-specific formatter (if present)

    If val is a RtorrentItem, fetch `field` from it before formatting. This
    is to allow `d|fmt('is_private')` vs. the redundant `d.is_private|fmt('is_private')`.
    Be aware that using the former in rtcontrol templates breaks the field auto-detection.
    """
    if field not in engine.FieldDefinition.FIELDS:
        return val
    if isinstance(val, rtorrent.RtorrentItem):
        val = getattr(val, field)
    formatter = engine.FieldDefinition.FIELDS[field].formatter
    if formatter:
        return formatter(val)
    return val


def fmt_pathext(val: str) -> str:
    """Extension of a path (including the '.')."""
    return os.path.splitext(val or "")[1]


def fmt_pathdir(val: str):
    """Directory containing the given path."""
    return os.path.dirname(val or "")


def fmt_json(val):
    """JSON serialization."""
    return json.dumps(val, cls=pymagic.JSONEncoder)


env = Environment(
    loader=FileSystemLoader([Path("~/.config/pyrosimple/templates/").expanduser()]),
)
env.filters.update(
    {name[4:]: method for name, method in globals().items() if name.startswith("fmt_")}
)


def expand_template(template_path: str, namespace: Dict) -> str:
    """Expand the given (preparsed) template.
    Currently, only jinja2 templates are supported.

    @param template: The name of the template, to be loaded by the jinja2 loaders.
    @param namespace: Custom namespace that is added to the predefined defaults
        and takes precedence over those.
    @return: The expanded template.
    @raise LoggableError: In case of typical errors during template execution.
    """
    template = env.get_template(template_path)
    # Default templating namespace
    # variables = dict(c=config.custom_template_helpers)
    variables = {}
    # Provided namespace takes precedence
    variables.update(namespace)
    # Expand template
    return template.render(**variables)


def format_item_str(
    template_str: str, item: Union[Dict, str, rtorrent.RtorrentItem], defaults=None
):
    """Simple helper function to format a string with an item"""
    template = env.from_string(template_str)
    return format_item(template, item, defaults)


def format_item(
    template: Template, item: Union[Dict, str, rtorrent.RtorrentItem], defaults=None
) -> str:
    """Format an item according to the given output template.

    @param format_spec: The output template, preparsed by jinja2.
    @param item: The object, which is automatically wrapped for interpolation.
    @param defaults: Optional default values.
    """
    if defaults is None:
        defaults = {}
    return str(template.render(d=item, **defaults))


def validate_field_list(
    fields: str,
    allow_fmt_specs=False,
):
    """Make sure the fields in the given list exist.

    @param fields: List of fields (comma-/space-separated if a string).
    @type fields: list or str
    @return: validated field names.
    @rtype: list
    """
    formats = [i[4:] for i in globals() if i.startswith("fmt_")]

    try:
        split_fields = [i.strip() for i in fields.split(",")]
    except AttributeError:
        # Not a string, expecting an iterable
        pass

    for name in split_fields:
        if allow_fmt_specs and "." in name:
            fullname = name
            name, fmtspecs = name.split(".", 1)
            for fmtspec in fmtspecs.split("."):
                if fmtspec not in formats and fmtspec != "raw":
                    raise error.UserError(
                        f"Unknown format specification {fmtspec!r} in {fullname!r}"
                    )

        if (
            name not in engine.FieldDefinition.FIELDS
            and not engine.TorrentProxy.add_manifold_attribute(name)
        ):
            raise error.UserError(f"Unknown field name {name!r}")

    return split_fields


def validate_sort_fields(sort_fields):
    """Make sure the fields in the given list exist, and return sorting key.

    If field names are prefixed with '-', sort order is reversed for that field (descending).
    """
    # Create sort specification
    sort_spec = tuple()
    for name in sort_fields.split(","):
        descending = False
        if name.startswith("-"):
            name = name[1:]
            descending = True
        sort_spec += ((name, descending),)

    # Validate field list
    validate_field_list(",".join([name for name, _ in sort_spec]))
    log = logging.getLogger(__name__)
    log.debug(
        "Sorting order is: %s",
        ", ".join([("-" if descending else "") + i for i, descending in sort_spec]),
    )

    # Need to provide complex key in order to allow for the minimum amount of attribute fetches,
    # since they could mean a potentially expensive RPC call.
    class Key:
        "Complex sort order key"

        def __init__(self, obj, *_):
            "Remember object to be compared"
            self.obj = obj

        def __lt__(self, other):
            "Compare to other key"
            for field, descending in sort_spec:
                lhs, rhs = getattr(self.obj, field), getattr(other.obj, field)
                if lhs == rhs:
                    continue
                return rhs < lhs if descending else lhs < rhs
            return False

    return Key


def get_fields_from_template(
    template: str, item_name: str = "d"
) -> Generator[str, None, None]:
    """Utility function to get field references from a template

    E.g: 'Name: {{d.size}}' -> ['size']"""
    for node in env.parse(template).find_all(jinja2.nodes.Getattr):
        if isinstance(node.node, jinja2.nodes.Name) and node.node.name == item_name:
            yield node.attr
