"""Contains some base jobs to reduce boilerplate across jobs"""
import logging

from typing import Dict, Optional

import pyrosimple

from pyrosimple import error
from pyrosimple.torrent import engine, rtorrent
from pyrosimple.util import matching, rpc


class BaseJob:
    """Set up a base job.

    Truthfully this setup is simple enough that it doesn't really need
    a base class, but it provides a concrete minimum example of what a
    custom job would need to look like.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.config.setdefault("dry_run", False)
        self.name = self.config.get("__job_name", self.__class__.__name__)
        url = None
        if "scgi_url" in self.config:
            url = pyrosimple.config.lookup_connection_alias(
                str(self.config.get("scgi_url"))
            )
        self.engine = pyrosimple.connect(url)

        self.log = logging.getLogger("pyrosimple.pyrotorque.jobs." + self.name)
        if "log_level" in self.config:
            self.log.setLevel(self.config["log_level"])
        self.log.debug("%s:%s created with config %r", __name__, self.name, self.config)

    def run(self):
        """Let all child classes determine what the action is."""
        raise NotImplementedError()


class MatchableJob(BaseJob):
    """Set up a job that loops through torrents that match a query and
    performs an action on each"""

    def __init__(self, config=None):
        super().__init__(config)
        self.config.setdefault("view", "main")
        sort = self.config.get("sort", "name,hash")
        query_tree = matching.QueryGrammar.parse(self.config["matcher"])
        sort_keys = [s[1:] if s.startswith("-") else s for s in sort.split(",")]

        self.matcher = matching.create_matcher(self.config["matcher"])
        self.sort_key = rtorrent.validate_sort_fields(sort)
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
            prefetch = [engine.FIELD_REGISTRY[f].requires for f in self.prefetch_fields]
            prefetch = [item for sublist in prefetch for item in sublist]
            view = self.engine.view(self.config["view"], self.matcher)
            matches = list(self.engine.items(view=view, prefetch=prefetch))
            matches.sort(key=self.sort_key)
            for i in matches:
                if self.matcher.match(i):
                    self.run_item(i)
        except (error.LoggableError, *rpc.ERRORS) as exc:
            self.log.warning(str(exc))
