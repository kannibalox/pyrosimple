"""Holds some tests that will only work on a live rTorrent instance"""
import os
import xmlrpc.client

from pathlib import Path

import pytest

import pyrosimple


live_only = pytest.mark.skipif(
    os.getenv("PYTEST_PYRO_LIVE", "false").lower() != "true",
    reason="live tests not enabled",
)


@live_only
def test_connect():
    engine = pyrosimple.connect()
    proxy = engine.open()
    proxy.system.hostname()
    with pytest.raises(pyrosimple.util.rpc.RpcError):
        proxy.fake_method()


@live_only
def test_pyroadmin():
    from pyrosimple.scripts.pyroadmin import AdminTool

    AdminTool().run(["config", "--check"])


@live_only
def test_load_tor():
    engine = pyrosimple.connect()
    proxy = engine.open()
    metapath = Path(Path(__file__).parent, "single.torrent")
    metafile = pyrosimple.util.metafile.Metafile.from_file(metapath)
    with metapath.open("rb") as fh:
        proxy.load.raw("", xmlrpc.client.Binary(fh.read()), "d.custom1.set=foobar")
    assert proxy.d.name(metafile.info_hash()) == metafile["info"]["name"]
    assert proxy.d.custom1(metafile.info_hash()) == "foobar"
    proxy.d.erase(metafile.info_hash())


@live_only
def test_cull_tor(tmpdir):
    from pyrosimple.scripts.rtcontrol import RtorrentControl

    engine = pyrosimple.connect()
    proxy = engine.open()
    metapath = Path(Path(__file__).parent, "single.torrent")
    metafile = pyrosimple.util.metafile.Metafile.from_file(metapath)
    dest = tmpdir.mkdir("data")
    rt = RtorrentControl()
    # Cull
    with metapath.open("rb") as fh:
        proxy.load.raw("", xmlrpc.client.Binary(fh.read()), f"d.directory.set={dest}")
    assert proxy.d.name(metafile.info_hash()) == metafile["info"]["name"]
    assert proxy.d.directory(metafile.info_hash()) == dest
    proxy.d.start(metafile.info_hash())
    rt.run([f"hash={metafile.info_hash()}", "--cull", "--yes", "-Q0"])
    with pytest.raises(pyrosimple.util.rpc.HashNotFound):
        for _ in range(0, 5):
            print(proxy.d.name(metafile.info_hash()))
            sleep(0.1)
