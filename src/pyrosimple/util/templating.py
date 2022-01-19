# -*- coding: utf-8 -*-
# pylint: disable=too-few-public-methods
""" Templating Helpers.

    Copyright (c) 2012 The PyroScope Project <pyroscope.project@gmail.com>
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

import os
from contextlib import closing


class InterpolationTemplate(object):
    """Simple string interpolation."""

    def __init__(self, fmt, mapping=None):
        """Create template ADT wrapper object."""
        try:
            self.fmt = str(fmt, "utf-8")
        except (TypeError, UnicodeDecodeError):
            self.fmt = fmt

        self.mapping = mapping or (lambda _: _)
        self.__engine__ = "interpolation"
        self.__file__ = None
        self.__text__ = ""

    def __repr__(self):
        """Returns interpolation string."""
        return self.fmt

    def __str__(self):
        """Returns interpolation string."""
        return self.fmt

    def substitute(self, **variables):
        """Return expanded template for given variable set."""
        return self.fmt % self.mapping(variables)


def preparse(template_text, lookup=None):
    """Do any special processing of a template, including recognizing the templating language
    and resolving file: references, then return an appropriate wrapper object.

    Currently Tempita and Python string interpolation are supported.
    `lookup` is an optional callable that resolves any ambiguous template path.
    """
    # First, try to resolve file: references to their contents
    template_path = None
    try:
        is_file = template_text.startswith("file:")
    except (AttributeError, TypeError):
        pass  # not a string
    else:
        if is_file:
            template_path = template_text[5:]
            if template_path.startswith("/"):
                template_path = "/" + template_path.lstrip("/")
            elif template_path.startswith("~"):
                template_path = os.path.expanduser(template_path)
            elif lookup:
                template_path = lookup(template_path)

            with closing(open(template_path, "r")) as handle:
                template_text = handle.read().rstrip()

    if hasattr(template_text, "__engine__"):
        # Already preparsed
        template = template_text
    else:
        if template_text.startswith("{{"):
            import tempita  # only on demand

            template = tempita.Template(template_text, name=template_path)
            template.__engine__ = "tempita"
        else:
            template = InterpolationTemplate(template_text)

        template.__file__ = template_path

    template.__text__ = template_text
    return template
