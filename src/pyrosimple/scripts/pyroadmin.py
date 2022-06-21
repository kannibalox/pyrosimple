""" Administration Tool.

    Copyright (c) 2010 The PyroScope Project <pyroscope.project@gmail.com>
"""


import pyrosimple

from pyrosimple import config
from pyrosimple.scripts.base import ScriptBase, ScriptBaseWithConfig


class AdminTool(ScriptBaseWithConfig):
    """Support for administrative tasks."""

    # TODO: config create, dump, set, get
    # TODO: backup session/config

    def add_options(self):
        super().add_options()
        subparsers = self.parser.add_subparsers()
        config_parser = subparsers.add_parser("config")
        config_parser.set_defaults(func=self.config)
        config_parser.add_argument(
            "--check", help="Check config for any issues", action="store_true"
        )

    def config(self):
        """Handle the config subcommand"""
        if self.args.check:
            try:
                config.autoload_scgi_url()
            except Exception:
                self.LOG.error("Error loading SCGI URL:")
                raise
            else:
                self.LOG.debug("Loaded SCGI URL successfully")
            try:
                pyrosimple.connect().open()
            except ConnectionRefusedError:
                self.LOG.warning(
                    "SCGI URL '%s' found, but rTorrent may not be running!",
                    config.autoload_scgi_url(),
                )
                raise
            else:
                self.LOG.debug("Connected to rTorrent successfully")

    def mainloop(self):
        self.args = self.parser.parse_args()
        self.args.func()


def run():  # pragma: no cover
    """The entry point."""
    ScriptBase.setup()
    AdminTool().run()


if __name__ == "__main__":
    run()
