# -*- coding: utf-8 -*-
""" Torrent Item Formatting and Filter Rule Parsing.

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

import json
import logging
import operator
import os
import re

from pathlib import Path
from typing import Callable, Dict, Optional, Union

from jinja2 import Environment, FileSystemLoader, Template

from pyrosimple import config, error
from pyrosimple.torrent import engine, rtorrent
from pyrosimple.util import fmt, pymagic


#
# Format specifiers
#
def fmt_sz(intval: int) -> str:
    """Format a byte sized value."""
    try:
        return fmt.human_size(intval)
    except (ValueError, TypeError):
        return "N/A".rjust(len(fmt.human_size(0)))


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


def fmt_subst(regex, subst):
    """Replace regex with string."""
    return lambda text: re.sub(regex, subst, text) if text else text


def fmt_mtime(val: str) -> float:
    """Modification time of a path."""
    p = Path(str(val))
    if p.exists():
        return p.stat().st_mtime
    else:
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
    """Apply a field-specific formatter (if present)"""
    if field not in engine.FieldDefinition.FIELDS:
        return val
    formatter = engine.FieldDefinition.FIELDS[field]._formatter
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
    loader=FileSystemLoader([Path("~/.pyroscope/templates").expanduser()]),
)
env.filters.update(
    dict(
        (name[4:], method)
        for name, method in globals().items()
        if name.startswith("fmt_")
    )
)

# TODO: All constant stuff should be calculated once, make this a class or something
# Also parse the template only once (possibly in config validation)!
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
    # Create helper namespace
    formatters = dict(
        (name[4:], method)
        for name, method in globals().items()
        if name.startswith("fmt_")
    )
    # Default templating namespace
    variables = dict(c=config.custom_template_helpers)
    variables.update(formatters)  # redundant, for backwards compatibility

    # Provided namespace takes precedence
    variables.update(namespace)

    # Expand template
    return template.render(**variables)


def format_item(
    template: Template, item: Union[Dict, str, rtorrent.RtorrentItem], defaults=None
) -> str:
    """Format an item according to the given output template.

    @param format_spec: The output template.
    @param item: The object, which is automatically wrapped for interpolation.
    @param defaults: Optional default values.
    """
    if defaults is None:
        defaults = {}
    # otemplate = env.from_string(format_spec)
    return str(template.render(d=item, **defaults))


def validate_field_list(
    fields: str,
    allow_fmt_specs=False,
    name_filter: Optional[Callable[[str], str]] = None,
):
    """Make sure the fields in the given list exist.

    @param fields: List of fields (comma-/space-separated if a string).
    @type fields: list or str
    @return: validated field names.
    @rtype: list
    """
    formats = [i[4:] for i in globals() if i.startswith("fmt_")]

    try:
        split_fields = [i.strip() for i in fields.replace(",", " ").split()]
    except AttributeError:
        # Not a string, expecting an iterable
        pass

    if name_filter:
        split_fields = [name_filter(name) for name in split_fields]

    for name in split_fields:
        if allow_fmt_specs and "." in name:
            fullname = name
            name, fmtspecs = name.split(".", 1)
            for fmtspec in fmtspecs.split("."):
                if fmtspec not in formats and fmtspec != "raw":
                    raise error.UserError(
                        "Unknown format specification %r in %r" % (fmtspec, fullname)
                    )

        if (
            name not in engine.FieldDefinition.FIELDS
            and not engine.TorrentProxy.add_manifold_attribute(name)
        ):
            raise error.UserError("Unknown field name %r" % (name,))

    return split_fields


def validate_sort_fields(sort_fields):
    """Make sure the fields in the given list exist, and return sorting key.

    If field names are prefixed with '-', sort order is reversed for that field (descending).
    """
    # Allow descending order per field by prefixing with '-'
    descending = set()

    def sort_order_filter(name: str) -> str:
        "Helper to remove flag and memoize sort order"
        if name.startswith("-"):
            name = name[1:]
            descending.add(name)
        return name

    # Split and validate field list
    sort_fields = validate_field_list(sort_fields, name_filter=sort_order_filter)
    log = logging.getLogger(__name__)
    log.debug(
        "Sorting order is: %s",
        ", ".join([("-" if i in descending else "") + i for i in sort_fields]),
    )

    # No descending fields?
    if not descending:
        return operator.attrgetter(*tuple(sort_fields))

    # Need to provide complex key
    class Key:
        "Complex sort order key"

        def __init__(self, obj, *_):
            "Remember object to be compared"
            self.obj = obj

        def __lt__(self, other):
            "Compare to other key"
            for field in sort_fields:
                lhs, rhs = getattr(self.obj, field), getattr(other.obj, field)
                if lhs == rhs:
                    continue
                return rhs < lhs if field in descending else lhs < rhs
            return False

    return Key
