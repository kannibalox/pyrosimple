from pathlib import Path

from pyrosimple.config import settings
from pyrosimple.scripts.pyroadmin import AdminTool


def test_pyroadmin_create_rc(tmp_path_factory):
    rc_path = Path(tmp_path_factory.mktemp("pyroadmin"), "rtorrent.rc")
    settings.RTORRENT_RC = str(rc_path)
    settings.CONFIG = "/dev/null"
    AdminTool().run(["config", "--create-rtorrent-rc"])


def test_pyroadmin_create_config(tmp_path_factory):
    config_path = Path(tmp_path_factory.mktemp("pyroadmin"), ".config", "config.toml")
    settings.RTORRENT_RC = "/dev/null"
    settings.CONFIG = str(config_path)
    AdminTool().run(["config", "--create-config"])
