# pylint: disable=missing-docstring
""" Data Types tests.
    Copyright (c) 2011-2020 The PyroScope Project <pyroscope.project@gmail.com>
"""
import pytest

from pyrosimple.util import parts


def test_bunch_janus():
    bunch = parts.Bunch()
    bunch.a = 1
    bunch["z"] = 2

    assert bunch["a"] == 1
    assert bunch.z == 2


def test_bunch_repr():
    bunch = repr(parts.Bunch(a=1, z=2))

    assert bunch.startswith("Bunch(")
    assert "a=" in bunch
    assert bunch.index("a=") < bunch.index("z=")


def test_bunch_no_attr():
    bunch = parts.Bunch()
    with pytest.raises(AttributeError):
        return bunch.not_there
