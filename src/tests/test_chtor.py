from pathlib import Path

import pytest

from pyrosimple.scripts.base import ScriptBase
from pyrosimple.scripts.lstor import MetafileLister
from pyrosimple.scripts.mktor import MetafileCreator
from pyrosimple.scripts.chtor import MetafileChanger
from pyrosimple.util.metafile import Metafile


@pytest.mark.parametrize(
    ("args", "field", "expected"),
    [
        (["-p"], ["info", "private"], 1),
        (["-P"], ["info", "private"], None),
        (["-s", "info.test=foo"], ["info", "test"], "foo"),
        # Tracker changes
        (
            ["-a", "http://example.com/announce.php/new_test"],
            ["announce"],
            "http://example.com/announce.php/new_test",
        ),
        (
            ["-a", "http://example.org/announce.php/new_test"],
            ["announce"],
            "http://example.com/announce.php/test",
        ),
        (
            ["--reannounce-all", "http://example.org/announce.php/new_test"],
            ["announce"],
            "http://example.org/announce.php/new_test",
        ),
    ],
)
def test_chtor(tmp_path_factory, args, field, expected):
    test_file = Path(tmp_path_factory.mktemp("mktor"), "hello.txt")
    torrent_file = test_file.with_suffix(".torrent")
    with test_file.open("w") as fh:
        fh.write("Hello world!")
    MetafileCreator().run([str(test_file), "http://example.com/announce.php/test"])
    args.append(str(torrent_file))
    MetafileChanger().run(args)
    metafile = Metafile.from_file(torrent_file)
    value = dict(metafile)
    for f in field:
        value = value.get(f, None)
    assert value == expected
