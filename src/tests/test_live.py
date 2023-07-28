"""Holds some tests that will only work """
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
    AdminTool().run(["config", "--dump-rc"])


@live_only
def test_load_tor():
    engine = pyrosimple.connect()
    proxy = engine.open()
    metapath = Path(Path(__file__).parent, "single.torrent")
    metafile = pyrosimple.util.metafile.Metafile.from_file(metapath)
    with metapath.open("rb") as fh:
        proxy.load.raw("", xmlrpc.client.Binary(fh.read()))
    assert proxy.d.name(metafile.info_hash()) == metafile["info"]["name"]
    proxy.d.erase(metafile.info_hash())
