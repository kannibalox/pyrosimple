"""Contains some base jobs to reduce boilerplate across jobs"""
from typing import Dict, Optional

import pyrosimple

from pyrosimple import error
from pyrosimple.torrent import engine, formatting, rtorrent
from pyrosimple.util import matching, pymagic, rpc


class BaseJob:
    """Set up a base job
    Truthfully this is simple enough that it doesn't really need to be used, but it provides a concrete minimum example of what a custom job would need to look like.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.config.setdefault("dry_run", False)
        self.engine = pyrosimple.connect()
        self.log = pymagic.get_class_logger(__name__)
        if "log_level" in self.config:
            self.log.setLevel(self.config["log_level"])
        self.log.debug("%s created with config %r", __name__, self.config)

    def run(self):
        """Let all child classes determine what the action is."""
        raise NotImplementedError()


class MatchableJob(BaseJob):
    """Set up a job that loops through torrents that match a query and performs an action on each"""

    def __init__(self, config=None):
        super().__init__(config)
        self.config.setdefault("view", "main")
        sort = self.config.get("sort", "name,hash")
        query_tree = matching.QueryGrammar.parse(self.config["matcher"])
        sort_keys = [s[1:] if s.startswith("-") else s for s in sort.split(",")]

        self.matcher = matching.create_matcher(self.config["matcher"])
        self.sort_key = formatting.validate_sort_fields(sort)
        self.prefetch_fields = [
            *matching.KeyNameVisitor().visit(query_tree),
            *sort_keys,
        ]

    def run_item(self, item: rtorrent.RtorrentItem):
        """Let all child classes determine what the action is."""
        raise NotImplementedError()

    def run(self):
        """Loop through matched torrents and perform the action.

        Note that there is not actual enforcement of dry_run here,
        that still needs to happen in run_item()"""
        try:
            self.engine.open()
            prefetch = [
                engine.FieldDefinition.FIELDS[f].requires for f in self.prefetch_fields
            ]
            prefetch = [item for sublist in prefetch for item in sublist]
            view = self.engine.view(self.config["view"], self.matcher)
            matches = list(self.engine.items(view=view, prefetch=prefetch))
            matches.sort(key=self.sort_key)
            for i in matches:
                if self.matcher.match(i):
                    self.run_item(i)
        except (error.LoggableError, *rpc.ERRORS) as exc:
            self.log.warning(str(exc))
