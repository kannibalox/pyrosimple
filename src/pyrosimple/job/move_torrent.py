"""Move a torrent to a remote host

Currently uses consistent hashing to determine which remote host
gets the torrent (if multiple are specified)."""
import hashlib

from typing import Dict, List

from pyrosimple import config
from pyrosimple.job import base
from pyrosimple.util import rpc


def nodes_by_hash_weight(meta_id: str, nodes: List[str]) -> Dict[str, int]:
    """Weight nodes by hashing the meta_id"""
    result = {
        n: int.from_bytes(hashlib.sha256(meta_id.encode() + n.encode()).digest(), "big")
        for n in nodes
    }
    return dict(sorted(result.items(), key=lambda item: item[1]))


class Mover(base.MatchableJob):
    """Move torrent to remote host(s)"""

    def __init__(self, job_config=None):
        """Initalize torrent mover job"""
        super().__init__(job_config)
        self.config["hosts"] = [
            config.lookup_connection_alias(h) for h in self.config["hosts"]
        ]

    def run_item(self, item):
        """Statistics logger job callback."""
        for host in nodes_by_hash_weight(item.hash + item.alias, self.config["hosts"]):
            rproxy = rpc.RTorrentProxy(host)
            metahash = item.hash
            try:
                rproxy.d.hash(item.hash)
            except rpc.HashNotFound:
                pass
            else:
                self.log.info(
                    "Hash %s already exists at remote URL %s", item.hash, host
                )
                continue
            if self.config["dry_run"]:
                self.log.info("Would move %s to %s", metahash, rproxy.system.hostname())
                break
            item.move_to_host(host)
            self.log.info("Moved %s to %s", metahash, rproxy.system.hostname())
            break
