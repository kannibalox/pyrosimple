# pylint: disable=
""" Traits tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
import logging
import unittest

import pytest

from pyrosimple.util import traits


@pytest.mark.parametrize(
    ("name", "alias", "filetype", "result"),
    [("Test", None, None, []), ("Test.tgz", None, ".tgz", ["misc", "tgz"])],
)
def test_trait_detect(name, alias, filetype, result):
    assert traits.detect_traits(name, alias, filetype) == result
