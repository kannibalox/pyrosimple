from pathlib import Path

from pyrosimple import config
from pyrosimple.scripts.pyroadmin import AdminTool


def test_pyroadmin_create_rc(tmp_path_factory):
    rc_path = Path(tmp_path_factory.mktemp("pyroadmin"), "rtorrent.rc")
    config.settings.RTORRENT_RC = str(rc_path)
    config.SETTINGS_FILE = "/dev/null"
    AdminTool().run(["config", "--create-rtorrent-rc"])
    assert rc_path.stat().st_size >	0


def test_pyroadmin_create_config(tmp_path_factory):
    config_path = Path(tmp_path_factory.mktemp("pyroadmin"), ".config", "config.toml")
    config.settings.RTORRENT_RC = "/dev/null"
    config.SETTINGS_FILE = str(config_path)
    AdminTool().run(["--verbose", "config", "--create-config"])
    assert config_path.stat().st_size > 0
