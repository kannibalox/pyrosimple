from pathlib import Path

import pytest

from pyrosimple.scripts.base import ScriptBase
from pyrosimple.scripts.chtor import MetafileChanger
from pyrosimple.scripts.lstor import MetafileLister
from pyrosimple.scripts.mktor import MetafileCreator
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
            ["--reannounce", "https://example.com/announce.php/test"],
            ["announce"],
            "https://example.com/announce.php/test",
        ),
        (
            ["--reannounce", "https://example.org/announce.php/test"],
            ["announce"],
            "http://example.com/announce.php/test",
        ),
        (
            ["--reannounce-all", "http://example.org/announce.php/new_test"],
            ["announce"],
            "http://example.org/announce.php/new_test",
        ),
        # Other
        (
            ["-s", "test=foo", "-T", "http://example.com"],
            ["test"],
            "foo",
        ),
        (
            ["-s", "test=foo", "-T", "http://example.org"],
            ["test"],
            None,
        ),
    ],
)
def test_lstor(tmp_path_factory, args, field, expected):
    test_file = Path(tmp_path_factory.mktemp("mktor"), "hello.txt")
    torrent_file = test_file.with_suffix(".torrent")
    with test_file.open("w") as fh:
        fh.write("Hello world!")
    MetafileCreator().run([str(test_file), "http://example.com/announce.php/test"])
    args.append(str(torrent_file))
    MetafileChanger().run(args)
    MetafileLister().run([str(torrent_file)])
