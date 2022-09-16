""" rTorrent Watch Jobs.

    Copyright (c) 2012 The PyroScope Project <pyroscope.project@gmail.com>
"""


import asyncio
import logging
import os
import time

from pathlib import Path
from typing import Any, Dict

from pyrosimple import config as configuration
from pyrosimple import error
from pyrosimple.scripts.base import ScriptBase, ScriptBaseWithConfig
from pyrosimple.torrent import rtorrent
from pyrosimple.util import metafile, pymagic, rpc
from pyrosimple.util.parts import Bunch


try:
    import pyinotify
except ImportError:
    pyinotify = Bunch(WatchManager=None, ProcessEvent=object)


class MetafileHandler:
    """Handler for loading metafiles into rTorrent."""

    def __init__(self, job, pathname: str):
        """Create a metafile handler."""
        self.metadata: metafile.Metafile
        self.job = job
        self.pathname = Path(pathname).resolve()
        self.ns: Dict[str, Any] = {
            "pathname": os.path.abspath(pathname),
            "info_hash": None,
            "tracker_alias": None,
        }

    def parse(self) -> bool:
        """Parse metafile and check pre-conditions."""
        try:
            if not os.path.getsize(self.pathname):
                # Ignore 0-byte dummy files (Firefox creates these while downloading)
                self.job.LOG.warning("Ignoring 0-byte metafile '%s'", self.pathname)
                return False

            self.metadata = metafile.Metafile.from_file(self.pathname)
            self.metadata.check_meta()
        except OSError as exc:
            self.job.LOG.error(
                "Can't read metafile '%s' (%s)",
                self.pathname,
                str(exc).replace(f": '{self.pathname}'", ""),
            )
            return False
        except ValueError as exc:
            self.job.LOG.error("Invalid metafile '%s': %s", self.pathname, exc)
            return False

        self.ns["info_hash"] = self.metadata.info_hash()
        self.ns["info_name"] = self.metadata["info"]["name"]
        self.job.LOG.info(
            "Loaded '%s' from metafile '%s'", self.metadata.info_hash(), self.pathname
        )

        # Check whether item is already loaded
        try:
            name = self.job.proxy.d.name(self.metadata.info_hash())
        except rpc.HashNotFound:
            pass
        except rpc.RpcError as exc:
            if exc.faultString != "Could not find info-hash.":
                self.job.LOG.error(
                    "While checking for #%s: %s", self.metadata.info_hash(), exc
                )
                return False
        else:
            self.job.LOG.warn(
                "Item #%s '%s' already added to client", self.metadata.info_hash(), name
            )
            if (
                self.job.config.get("remove_already_added", False)
                and not self.job.config["dry_run"]
            ):
                Path(self.pathname).unlink()
            return False

        return True

    def addinfo(self) -> None:
        """Add known facts to templating namespace."""
        # Basic values
        self.ns["watch_path"] = self.job.config["path"]
        self.ns["relpath"] = None
        for watch in self.job.config["path"]:
            path = Path(self.pathname)
            try:
                self.ns["relpath"] = path.relative_to(watch)
                break
            except ValueError:
                pass

        # Build indicator flags for target state from filename
        flags = str(self.pathname).split(os.sep)
        flags.extend(flags[-1].split("."))
        self.ns["flags"] = {i for i in flags if i}

        # Metafile stuff
        announce = self.metadata.get("announce", None)
        if announce:
            self.ns["tracker_alias"] = configuration.map_announce2alias(announce)

        main_file = self.ns["info_name"]
        if "files" in self.metadata["info"]:
            main_file = list(
                sorted(
                    (i["length"], i["path"][-1]) for i in self.metadata["info"]["files"]
                )
            )[-1][1]
        self.ns["filetype"] = os.path.splitext(main_file)[1]

        # Finally, expand commands from templates
        self.ns["commands"] = []
        for key, cmd in sorted(self.job.custom_cmds.items()):
            try:
                template = rtorrent.env.from_string(cmd)
                for split_cmd in rtorrent.format_item(
                    template, {}, defaults=self.ns
                ).split():
                    self.ns["commands"].append(split_cmd.strip())
            except error.LoggableError as exc:
                self.job.LOG.error(f"While expanding '{key}' custom command: {exc}")

    def load(self) -> None:
        """Load metafile into client."""
        if not self.metadata.info_hash() and not self.parse():
            return

        self.addinfo()

        try:
            # TODO: Scrub metafile if requested

            # Determine target state
            start_it = self.job.config.get("load_mode", "").lower() in (
                "start",
                "started",
            )

            if "start" in self.ns["flags"]:
                start_it = True
            elif "load" in self.ns["flags"]:
                start_it = False

            # Load metafile into client
            load_cmd = self.job.proxy.load.verbose
            if start_it:
                load_cmd = self.job.proxy.load.start_verbose

            self.job.LOG.debug(
                "Templating values are:\n    %s"
                % "\n    ".join(
                    f"{key}={repr(val)}" for key, val in sorted(self.ns.items())
                )
            )

            if self.job.config["dry_run"]:
                self.job.LOG.info(
                    f"Would load: {self.pathname} with commands {self.ns['commands']}"
                )
                return

            self.job.LOG.debug(
                f"Loading {self.pathname} with commands {self.ns['commands']}"
            )

            load_cmd(rpc.NOHASH, str(self.pathname), *tuple(self.ns["commands"]))
            time.sleep(0.05)  # let things settle

            # Announce new item
            if self.job.config["print_to_client"]:
                try:
                    name = self.job.proxy.d.name(self.metadata.info_hash())
                except rpc.HashNotFound:
                    name = "NOHASH"
                msg = "{}: Loaded '{}' from '{}/' {}".format(
                    self.job.__class__.__name__,
                    name,
                    os.path.dirname(self.pathname).rstrip(os.sep),
                    "[started]" if start_it else "[normal]",
                )
                self.job.proxy.log(rpc.NOHASH, msg)

            # TODO: Evaluate fields and set client values
            # TODO: Add metadata to tied file if requested

            # TODO: Execute commands AFTER adding the item, with full templating
            # Example: Labeling - add items to a persistent view, i.e. "postcmd = view.set_visible={{label}}"
            #   could also be done automatically from the path, see above under "flags" (autolabel = True)
            #   and add traits to the flags, too, in that case

        except rpc.ERRORS as exc:
            self.job.LOG.error("While loading #%s: %s", self.metadata.info_hash(), exc)

    def handle(self):
        """Handle metafile."""
        if self.parse():
            self.load()


class RemoteWatch:
    """rTorrent remote torrent file watch."""

    def __init__(self, config=None):
        """Set up remote watcher."""
        self.config = config or {}
        self.LOG = pymagic.get_class_logger(self)
        self.LOG.debug("Remote watcher created with config %r", self.config)

    def run(self):
        """Check remote watch target."""
        # TODO: ftp. ssh, and remote rTorrent instance (extra view?) as sources!
        # config:
        #   local_dir   storage path (default local sessiondir + '/remote-watch-' + jobname
        #   target      URL of target to watch


class TreeWatchHandler(pyinotify.ProcessEvent):
    """inotify event handler for rTorrent folder tree watch.

    See https://github.com/seb-m/pyinotify/.
    """

    METAFILE_EXT = (".torrent", ".load", ".start", ".queue")

    def handle_path(self, event):
        """Handle a path-related event."""
        self.job.LOG.debug(f"Notification {event!r}")
        if event.dir:
            return

        if any(event.pathname.endswith(i) for i in self.METAFILE_EXT):
            MetafileHandler(self.job, event.pathname).handle()
        elif os.path.basename(event.pathname) == "watch.ini":
            self.job.LOG.info(f"NOT YET Reloading watch config for '{event.path}'")
            # TODO: Load new metadata

    def process_IN_CLOSE_WRITE(self, event):
        """File written."""
        # <Event dir=False name=xx path=/var/torrent/watch/tmp pathname=/var/torrent/watch/tmp/xx>
        self.handle_path(event)

    def process_IN_MOVED_TO(self, event):
        """File moved into tree."""
        # <Event dir=False name=yy path=/var/torrent/watch/tmp pathname=/var/torrent/watch/tmp/yy>
        self.handle_path(event)

    def process_default(self, event):
        """Fallback."""
        if self.job.LOG.isEnabledFor(logging.DEBUG):
            # On debug level, we subscribe to ALL events, so they're expected in that case ;)
            if self.job.config["trace_inotify"]:
                self.job.LOG.debug(f"Ignored inotify event:\n    {event!r}")
        else:
            self.job.LOG.warning(f"Unexpected inotify event {event!r}")


class TreeWatch:
    """rTorrent folder tree watch via inotify."""

    def __init__(self, config=None):
        self.config = config or {}
        self.LOG = pymagic.get_class_logger(self)
        if "log_level" in self.config:
            self.LOG.setLevel(config["log_level"])
        self.LOG.debug("Tree watcher created with config %r", self.config)
        self.config.setdefault("print_to_client", True)
        self.config.setdefault("dry_run", False)
        self.config.setdefault("started", False)
        self.config.setdefault("trace_inotify", False)
        self.config.setdefault("check_unhandled", False)
        self.config.setdefault("remove_unhandled", False)
        self.config.setdefault("remove_already_added", False)

        self.manager = None
        self.handler = None
        self.notifier = None

        if "path" not in self.config:
            raise error.UserError("You need to set 'path' in the configuration!")

        self.config["path"] = {
            Path(p).expanduser().absolute()
            for p in self.config["path"].split(os.pathsep)
        }
        for path in self.config["path"]:
            if not path.is_dir():
                raise error.UserError(f"Path '{path}' is not a directory!")

        # Assemble custom commands
        self.custom_cmds = {}
        for key, val in self.config.items():
            if key.startswith("cmd_"):
                self.custom_cmds[key] = val

        # Get client proxy
        self.proxy = rpc.RTorrentProxy(configuration.settings.SCGI_URL)

        self.setup()

    def setup(self):
        """Set up inotify manager.

        See https://github.com/seb-m/pyinotify/.
        """
        if not pyinotify.WatchManager:
            raise error.UserError(
                f"You need to install 'pyinotify' to use {self.__class__.__name__}!"
            )

        self.manager = pyinotify.WatchManager()
        self.handler = TreeWatchHandler(job=self)
        self.notifier = pyinotify.AsyncNotifier(self.manager, self.handler)

        if self.LOG.isEnabledFor(logging.DEBUG):
            mask = pyinotify.ALL_EVENTS
        else:
            mask = (
                pyinotify.IN_CLOSE_WRITE  # pylint: disable=no-member
                | pyinotify.IN_MOVED_TO  # pylint: disable=no-member
            )

        # Add all configured base dirs
        for path in self.config["path"]:
            self.manager.add_watch(path, mask, rec=True, auto_add=True)

    def run(self):
        """Regular maintenance and fallback task."""
        if self.config.get("check_unhandled", False):
            for path in self.config["path"]:
                for filepath in Path(path).rglob("**/*.torrent"):
                    MetafileHandler(self, filepath).handle()
                    if (
                        self.config.get("remove_unhandled", False)
                        and filepath.exists()
                        and not self.config["dry_run"]
                    ):
                        filepath.unlink()


class TreeWatchCommand(ScriptBaseWithConfig):
    """
    Use tree watcher directly from cmd line, call it like this:
        python -m pyrosimple.torrent.watch <DIR>

    If the argument is a file, the templating namespace for that metafile is
    dumped (for testing and debugging purposes).
    """

    # log level for user-visible standard logging
    STD_LOG_LEVEL = logging.DEBUG

    # argument description for the usage information
    ARGS_HELP = "<directory>"

    def mainloop(self):
        """The main loop."""
        # Print usage if not enough args or bad options
        if len(self.args) < 1:
            self.parser.error(
                "You have to provide the root directory of your watch tree, or a metafile path!"
            )

        pathname = os.path.abspath(self.args[0])
        if os.path.isdir(pathname):
            watch = TreeWatch(
                Bunch(
                    path=pathname,
                    job_name="watch",
                    active=True,
                    dry_run=True,
                    load_mode=None,
                )
            )
            asyncio.sleep(0)
        else:
            config = Bunch()
            config.update(
                {
                    key.split(".", 2)[-1]: val
                    for key, val in configuration.settings.TORQUE.items()
                    if key.startswith("job.treewatch.")
                }
            )
            config.update(
                dict(
                    path=os.path.dirname(os.path.dirname(pathname)),
                    job_name="treewatch",
                    active=False,
                    dry_run=True,
                )
            )
            watch = TreeWatch(config)
            handler = MetafileHandler(watch, pathname)

            ok = handler.parse()
            self.LOG.debug(
                "Metafile '%s' would've %sbeen loaded", pathname, ("" if ok else "NOT ")
            )

            if ok:
                handler.addinfo()
                self.LOG.info(
                    "Templating values are:\n    %s",
                    "\n    ".join(
                        f"{key}={repr(val)}" for key, val in sorted(handler.ns.items())
                    ),
                )

    @classmethod
    def main(cls):
        """The entry point."""
        ScriptBase.setup()
        cls().run()


if __name__ == "__main__":
    TreeWatchCommand.main()
