# -*- coding: utf-8 -*-
# pylint: disable=
""" Traits tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""
import logging
import unittest

import pytest

from pyrosimple.util import traits

@pytest.mark.parametrize(
    ('name', "alias", "filetype", "result"),
    [
        ('Test', None, None, []),
        ('Test.tgz', None, '.tgz', ['misc', 'tgz'])
    ]
)
def test_trait_detect(name, alias, filetype, result):
    assert traits.detect_traits(name, alias, filetype) == result
