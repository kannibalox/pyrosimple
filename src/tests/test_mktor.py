from pathlib import Path

import pytest

from pyrosimple.scripts.base import ScriptBase
from pyrosimple.scripts.lstor import MetafileLister
from pyrosimple.scripts.mktor import MetafileCreator
from pyrosimple.util.metafile import Metafile


def test_mktor(tmp_path_factory):
    test_file = Path(tmp_path_factory.mktemp("mktor"), "hello.txt")
    with test_file.open("w") as fh:
        fh.write("Hello world!")
    MetafileCreator().run([str(test_file), "http://example.com"])
    MetafileLister().run([str(test_file.with_suffix(".torrent"))])


def test_mktor_magnet(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("mktor")
    magnet_string = (
        "magnet:?xt=urn:btih:1447bb03de993e1ee7e430526ff1fbac0daf7b44&dn=hello.txt"
    )
    MetafileCreator().run([magnet_string, "--magnet-watch", str(tmp_path)])
    Metafile.from_file(
        Path(
            tmp_path,
            "magnet-hello.txt-1447bb03de993e1ee7e430526ff1fbac0daf7b44.torrent",
        )
    )["magnet-uri"] == magnet_string


def test_mktor_output(tmp_path_factory):
    test_file = Path(tmp_path_factory.mktemp("mktor"), "hello.txt")
    out_file = Path(tmp_path_factory.mktemp("mktor"), "out.torrent")
    with test_file.open("w") as fh:
        fh.write("Hello world!")
    MetafileCreator().run([str(test_file), "http://example.com", "-o", str(out_file)])
    MetafileLister().run([str(out_file)])
