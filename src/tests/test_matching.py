# -*- coding: utf-8 -*-
# pylint: disable=
""" Filter condition tests.

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
import time
import unittest

import pytest

import parsimonious

from pyrosimple.util import matching
from pyrosimple.util.parts import Bunch


log = logging.getLogger(__name__)
log.debug("module loaded")


@pytest.mark.parametrize(
    "cond",
    [
        "//",
        "/test/",
        "/.*/",
        "name=*test*",
        "name=//",
        "name!=//",
        "name=/test/",
        "name=/.*/",
        "Roger.Rabbit?",
        "name=Roger.Rabbit?",
        "Bang!Bang!Bang!",
        "name=Bang!Bang!Bang!",
        "Æon",
        "name=*Æon*",
        "name==test",
        "number=0",
        "number>0",
        "number>=0",
        "number=+0",
        "number<0",
        "number<=0",
        "number=-0",
        "name=/[0-9]/",
        "number!=0",
        "number<>0",
        "name==/.*/",
        "name=*test*",
        "name=test-test2.mkv",
        'name="The Thing"',
        'name="*The Thing*"',
        "name=test name=test2",
        "name=test OR name=test2",
        "[ name=test OR name=test2 ]",
        "NOT [ name=test OR name=test2 ]",
        "NOT [ name=test name=test2 ]",
        "NOT [ name=test test2 ]",
        "NOT [ name=test OR alias=// ]",
        "test=five [ name=test OR name=test2 ]",
        "test=five NOT [ name=test OR name=test2 ]",
        "test=five OR NOT [ name=test name=test2 ]",
        "test=five OR NOT [ name=test OR name=test2 ]",
    ],
)
def test_parsim_good_conditions(cond):
    matching.QueryGrammar.parse(cond)


@pytest.mark.parametrize(
    "cond",
    [
        "",
        "NOT",
        "NOT OR",
        "name=name=name",
        "name!="
        "name=="
    ],
)
def test_parsim_error_conditions(cond):
    with pytest.raises(parsimonious.exceptions.ParseError):
        matching.QueryGrammar.parse(cond)

if __name__ == "__main__":
    unittest.main()
