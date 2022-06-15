"""Move a torrent to a remote host

Currently uses consistent hashing to determine which remote host
gets the torrent (if multiple are specified)."""
import hashlib
import os
import xmlrpc.client

from pathlib import Path
from time import sleep
from typing import Dict, List

import bencode

import pyrosimple

from pyrosimple import error
from pyrosimple.util import matching, metafile, pymagic, rpc


def nodes_by_hash_weight(meta_id: str, nodes: List[str]) -> Dict[str, int]:
    """Weight nodes by hashing the meta_id"""
    result = {
        n: int.from_bytes(hashlib.sha256(meta_id.encode() + n.encode()).digest(), "big")
        for n in nodes
    }
    return dict(sorted(result.items(), key=lambda item: item[1]))


def get_custom_fields(infohash, proxy):
    """Try using rtorrent-ps commands to list custom keys, otherwise fall back to reading from a session file."""
    if "d.custom.keys" in proxy.system.listMethods():
        custom_fields = {}
        for key in proxy.d.custom.keys(infohash):
            custom_fields[key] = proxy.d.custom(infohash, key)
    else:
        info_file = Path(proxy.session.path(), f"{infohash}.torrent.rtorrent")
        proxy.d.save_full_session(infohash)
        with open(info_file, "rb") as fh:
            custom_fields = bencode.bread(fh)["custom"]
    return custom_fields


class Mover:
    """Move torrent to remote host(s)"""

    def move(
        self,
        infohash,
        remote_proxy,
        fast_resume=True,
        extra_cmds=None,
        keep_basedir=True,
        copy=False,
    ):
        """Moves a torrent to a specific host"""
        if extra_cmds is None:
            extra_cmds = []
        self.LOG.debug(
            "Attempting to %s %s",
            "copy" if copy else "move",
            infohash,
        )
        try:
            remote_proxy.d.hash(infohash)
        except rpc.HashNotFound:
            pass
        else:
            self.LOG.warning("Hash exists remotely")
            return False

        torrent = bencode.bread(
            os.path.join(self.proxy.session.path(), f"{infohash}.torrent")
        )

        if keep_basedir:
            esc_basedir = self.proxy.d.directory_base(infohash).replace('"', '"')
            extra_cmds.insert(0, f'd.directory_base.set="{esc_basedir}"')

        if self.proxy.d.complete(infohash) == 1 and fast_resume:
            self.LOG.debug(
                "Setting fast resume data from %s",
                self.proxy.d.directory_base(infohash),
            )
            metafile.add_fast_resume(torrent, self.proxy.d.directory_base(infohash))

        xml_metafile = xmlrpc.client.Binary(bencode.bencode(torrent))

        if not copy:
            self.proxy.d.stop(infohash)
        self.LOG.debug("Running extra commands on load: %s", extra_cmds)
        remote_proxy.load.raw("", xml_metafile, *extra_cmds)
        for _ in range(0, 5):
            try:
                remote_proxy.d.hash(infohash)
            except rpc.HashNotFound:
                sleep(1)
        # After 5 seconds, let the exception happen
        remote_proxy.d.hash(infohash)

        # Keep custom values
        for k, v in get_custom_fields(infohash, self.proxy).items():
            remote_proxy.d.custom.set(infohash, k, v)
        for key in range(1, 5):
            value = getattr(self.proxy.d, f"custom{key}")(infohash)
            getattr(remote_proxy.d, f"custom{key}.set")(infohash, value)

        if fast_resume:
            remote_proxy.d.start(infohash)
        if not copy:
            self.proxy.d.erase(infohash)
        return True

    def __init__(self, config=None):
        """Initalize torrent mover job"""
        self.config = config or {}
        self.LOG = pymagic.get_class_logger(self)
        self.LOG.debug("Statistics logger created with config %r", self.config)
        self.config.setdefault("dry_run", False)
        self.proxy = None
        self.engine = None

    def run(self):
        """Statistics logger job callback."""
        try:
            self.engine = pyrosimple.connect()
            self.proxy = self.engine.open()
            matcher = matching.create_matcher(self.config["matcher"])
            hosts = self.config["hosts"]
            if not isinstance(hosts, list):
                hosts = [hosts]
            for i in self.engine.view("default", matcher):
                for host in nodes_by_hash_weight(i.hash + i.alias, hosts):
                    rproxy = rpc.RTorrentProxy(host)
                    metahash = i.hash
                    if self.config["dry_run"]:
                        self.LOG.info(
                            "Would move %s to %s", metahash, rproxy.system.hostname()
                        )
                        break
                    if self.move(metahash, rproxy):
                        self.LOG.info(
                            "Moved %s to %s", metahash, rproxy.system.hostname()
                        )
                        break
        except (error.LoggableError, *rpc.ERRORS) as exc:
            self.LOG.warning(str(exc))
