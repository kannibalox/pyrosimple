""" Administration Tool.

    Copyright (c) 2010 The PyroScope Project <pyroscope.project@gmail.com>
"""
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

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
