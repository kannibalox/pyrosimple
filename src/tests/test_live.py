"""Holds some tests that will only work """
import os

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
