"""A simple job to emulate rtcontrol's actions"""
from pyrosimple import error
from pyrosimple.job.base import MatchableJob, BaseJob
from pyrosimple.torrent import formatting, rtorrent

import subprocess

class Command(BaseJob):
    """Runs a single untemplated command."""
    def __init__(self, config=None):
        super().__init__(config)
        self.args = self.config.get("args", [])
        allowed_kwargs = ["shell", "cwd", "timeout", "check", "env"]
        self.kwargs = {k: self.config[k] for k in allowed_kwargs if k in self.config}

    def run(self):
        if not self.config['dry_run']:
            proc = subprocess.run(self.args, **self.kwargs, capture_output=True)
            self.log.info("Command %s finished with RC=%s", proc.cmd, proc.returncode)
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
        self.args = [formatting.env.from_string(a) for a in self.config.get("args", [])]

    def run_item(self, item):
        """For now, simply call the named methods on the item"""
        action = self.config["action"]
        processed_args = [formatting.format_item(a, item) for a in self.args]
        if self.config["dry_run"]:
            self.log.info(
                "Would %s(%s) %s",
                action,
                "" if not processed_args else processed_args,
                item.hash,
            )
        else:
            getattr(item, self.action)(*processed_args)
