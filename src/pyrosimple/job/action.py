"""A simple job to emulate rtcontrol's actions"""
import subprocess

from pyrosimple import error
from pyrosimple.job.base import BaseJob, MatchableJob
from pyrosimple.torrent import rtorrent


class Command(BaseJob):
    """Runs a single untemplated command."""

    def __init__(self, config=None):
        super().__init__(config)
        self.args = self.config.get("args", [])
        allowed_kwargs = ["shell", "cwd", "timeout", "check", "env"]
        self.kwargs = {k: self.config[k] for k in allowed_kwargs if k in self.config}

    def run(self):
        if not self.config["dry_run"]:
            proc = subprocess.run(  # pylint: disable=subprocess-run-check
                self.args, **self.kwargs, capture_output=True
            )
            self.log.info("Command %s finished with RC=%s", proc.args, proc.returncode)
            self.log.debug("stdout: %s", proc.stdout)
            self.log.debug("stderr: %s", proc.stderr)
        else:
            self.log.info("Would run %s with parameters %s", self.args, self.kwargs)


class ItemCommand(MatchableJob):
    """Runs a templated command against matching items."""

    def __init__(self, config=None):
        super().__init__(config)
        self.args = [rtorrent.env.from_string(a) for a in self.config.get("args", [])]
        allowed_kwargs = ["shell", "cwd", "timeout", "check", "env"]
        self.kwargs = {k: self.config[k] for k in allowed_kwargs if k in self.config}

    def run_item(self, item):
        if not self.config["dry_run"]:
            proc = subprocess.run(  # pylint: disable=subprocess-run-check
                [rtorrent.format_item(a, item) for a in self.args],
                **self.kwargs,
                capture_output=True,
            )
            self.log.info("Command %s finished with RC=%s", proc.args, proc.returncode)
            self.log.debug("stdout: %s", proc.stdout)
            self.log.debug("stderr: %s", proc.stderr)
        else:
            self.log.info("Would run %s with parameters %s", self.args, self.kwargs)


class Action(MatchableJob):
    """Run an action for each matched item"""

    def __init__(self, config=None):
        super().__init__(config)
        self.action = self.config["action"]
        if not hasattr(rtorrent.RtorrentItem, self.action):
            raise error.ConfigurationError(f"Action '{self.action}' not found!")
        self.args = [rtorrent.env.from_string(a) for a in self.config.get("args", [])]

    def run_item(self, item):
        """For now, simply call the named methods on the item"""
        action = self.config["action"]
        processed_args = [rtorrent.format_item(a, item) for a in self.args]
        if self.config["dry_run"]:
            self.log.info(
                "Would %s(%s) %s",
                action,
                "" if not processed_args else processed_args,
                item.hash,
            )
        else:
            getattr(item, self.action)(*processed_args)
