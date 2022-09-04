""" Administration Tool.

    Copyright (c) 2010 The PyroScope Project <pyroscope.project@gmail.com>
"""

from datetime import datetime
from pathlib import Path

import pyrosimple

from pyrosimple import config
from pyrosimple.scripts.base import ScriptBase, ScriptBaseWithConfig
from pyrosimple.util import matching


class AdminTool(ScriptBaseWithConfig):
    """Support for administrative tasks."""

    # TODO: config create, dump, set, get
    # TODO: backup session/config

    def add_options(self):
        super().add_options()
        self.parser.set_defaults(func=None)
        subparsers = self.parser.add_subparsers()
        config_parser = subparsers.add_parser("config", help="Validate configuration")
        config_parser.set_defaults(func=self.config)
        config_parser.add_argument(
            "--check", help="Check config for any issues", action="store_true"
        )
        backfill_parser = subparsers.add_parser(
            "backfill", help="Backfill missing custom fields from available data"
        )
        backfill_parser.set_defaults(func=self.backfill)
        backfill_parser.add_argument(
            "--dry-run",
            help="Print changes instead of applying them",
            action="store_true",
        )

    def backfill(self):
        """Backfill missing any missing metadata from available sources.
        Safe to run multiple times.
        """
        # pylint: disable=broad-except
        engine = pyrosimple.connect()
        engine.open()
        for i in engine.view("main", matching.create_matcher("loaded=0 metafile=/.+/")):
            try:
                mtime = int(Path(i.metafile).stat().st_mtime)
                if self.args.dry_run:
                    dt = datetime.fromtimestamp(mtime)
                    print(
                        f"Would set {i.hash} tm_loaded to {dt} from metafile {i.metafile}"
                    )
                else:
                    i.rpc_call("d.custom.set", ["tm_loaded", str(mtime)])
                    i.flush()
            except Exception as e:
                print(f"Could not set tm_loaded for {i.hash}: {e}")
        for i in engine.view("main", matching.create_matcher("loaded=0 path=/.+/")):
            try:
                mtime = int(Path(i.path).stat().st_mtime)
                if self.args.dry_run:
                    dt = datetime.fromtimestamp(mtime)
                    print(f"Would set {i.hash} tm_loaded to {dt} from path {i.path}")
                else:
                    i.rpc_call("d.custom.set", ["tm_loaded", str(mtime)])
                    i.flush()
            except Exception as e:
                print(f"Could not set tm_loaded for {i.hash}: {e}")
        for i in engine.view(
            "main", matching.create_matcher("completed=0 is_complete=yes path=/.+/")
        ):
            try:
                mtime = int(Path(i.path).stat().st_mtime)
                if self.args.dry_run:
                    dt = datetime.fromtimestamp(mtime)
                    print(f"Would set {i.hash} tm_completed to {dt} from path {i.path}")
                else:
                    i.rpc_call("d.custom.set", ["tm_completed", str(mtime)])
                    i.flush()
            except Exception as e:
                print(f"Could not set tm_loaded for {i.hash}: {e}")

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
                self.LOG.error(
                    "SCGI URL '%s' found, but rTorrent may not be running!",
                    config.autoload_scgi_url(),
                )
                raise
            else:
                self.LOG.info("Connected to rTorrent successfully")

    def mainloop(self):
        self.args = self.parser.parse_args()
        if self.args.func is None:
            self.parser.print_help()
            return
        self.args.func()


def run():  # pragma: no cover
    """The entry point."""
    ScriptBase.setup()
    AdminTool().run()


if __name__ == "__main__":
    run()
