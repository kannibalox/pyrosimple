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
        (["-s", "info.files=+1", "-V"], ["info", "files"], 1),
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


def test_chtor_output_dir(tmp_path_factory):
    test_file = Path(tmp_path_factory.mktemp("mktor"), "hello.txt")
    torrent_file = test_file.with_suffix(".torrent")
    target_output_file = Path(tmp_path_factory.mktemp("mktor-new"), "hello.torrent")
    with test_file.open("w") as fh:
        fh.write("Hello world!")
    MetafileCreator().run([str(test_file), "http://example.com/announce.php/test"])
    MetafileChanger().run(
        ["-RC", "-o", str(target_output_file.parent), str(torrent_file)]
    )
    metafile = Metafile.from_file(target_output_file)
    assert metafile.check_meta() is None
