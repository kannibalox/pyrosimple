"""A simple job to emulate rtcontrol's actions"""
from pyrosimple import error
from pyrosimple.job.base import MatchableJob
from pyrosimple.torrent import formatting, rtorrent


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
