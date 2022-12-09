import pytest

from pathlib import Path

from pyrosimple.scripts.base import ScriptBase
from pyrosimple.scripts.mktor import MetafileCreator
from pyrosimple.scripts.lstor import MetafileLister

def test_mktor(tmp_path_factory):
    test_file = Path(tmp_path_factory.mktemp("mktor"), "hello.txt")
    with test_file.open("w") as fh:
        fh.write("Hello world!")
    ScriptBase.setup()
    MetafileCreator().run([str(test_file), "http://example.com"])
    MetafileLister().run([str(test_file.with_suffix(".torrent"))])
