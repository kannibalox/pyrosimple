from pathlib import Path

import pytest

from pyrosimple.scripts.base import ScriptBase
from pyrosimple.scripts.lstor import MetafileLister
from pyrosimple.scripts.mktor import MetafileCreator


def test_mktor(tmp_path_factory):
    test_file = Path(tmp_path_factory.mktemp("mktor"), "hello.txt")
    with test_file.open("w") as fh:
        fh.write("Hello world!")
    ScriptBase.setup()
    MetafileCreator().run([str(test_file), "http://example.com"])
    MetafileLister().run([str(test_file.with_suffix(".torrent"))])


def test_mktor_output(tmp_path_factory):
    test_file = Path(tmp_path_factory.mktemp("mktor"), "hello.txt")
    out_file = Path(tmp_path_factory.mktemp("mktor"), "out.torrent")
    with test_file.open("w") as fh:
        fh.write("Hello world!")
    ScriptBase.setup()
    MetafileCreator().run([str(test_file), "http://example.com", "-o", str(out_file)])
    MetafileLister().run([str(out_file)])
