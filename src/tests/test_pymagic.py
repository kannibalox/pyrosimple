# pylint: disable=
""" Python utilities tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
import logging
import unittest

from pyrosimple.util import pymagic


log = logging.getLogger(__name__)
log.debug("module loaded")


class ImportTest(unittest.TestCase):
    def test_import_name(self):
        docstr = pymagic.import_name("pyrosimple", "__doc__")
        assert "Core Package" in docstr

        docstr = pymagic.import_name("pyrosimple.util", "__doc__")
        assert "Utility Modules" in docstr

    def test_import_fail(self):
        try:
            pymagic.import_name("pyrosimple.does_not_exit", "__doc__")
        except ImportError as exc:
            assert "pyrosimple.does_not_exit" in str(exc), str(exc)
        else:
            assert False, "Import MUST fail!"

    def test_import_colon(self):
        docstr = pymagic.import_name("pyrosimple:__doc__")
        assert "Core Package" in docstr

    def test_import_missing_colon(self):
        try:
            pymagic.import_name("pyrosimple")
        except ValueError as exc:
            assert "pyrosimple" in str(exc), str(exc)
        else:
            assert False, "Import MUST fail!"


class LogTest(unittest.TestCase):
    def test_get_class_logger(self):
        logger = pymagic.get_class_logger(self)
        assert logger.name == "tests.test_pymagic.LogTest"


if __name__ == "__main__":
    unittest.main()
