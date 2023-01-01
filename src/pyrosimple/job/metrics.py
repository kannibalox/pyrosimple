"""Jobs for metric reporting"""
from collections import Counter
from threading import Thread
from time import sleep, time
from typing import Any, Dict, List, Optional

from prometheus_client import REGISTRY, exposition
from prometheus_client.core import Counter as PromCounter
from prometheus_client.core import Gauge, Info

from pyrosimple import error
from pyrosimple.job.base import BaseJob
from pyrosimple.util import fmt, rpc


class EngineStats(BaseJob):
    """Simple rTorrent connection statistics logger."""

    def run(self):
        """Statistics logger job callback."""
        try:
            self.engine.open()
            self.log.info(
                "Stats for %s - up %s, %s torrents",
                self.engine.engine_id,
                fmt.human_duration(
                    self.engine.rpc.system.time() - self.engine.startup, 0, 2, True
                ).strip(),
                self.engine.rpc.view.size(rpc.NOHASH, "default"),
            )
        except (error.LoggableError, *rpc.ERRORS) as exc:
            self.log.warning(str(exc))


class RtorrentExporter(BaseJob):
    """Expose rTorrent and host statistics for scraping by a
    Prometheus instance."""

    def add_metric(self, name, cls, *args, **kwargs):
        """Only add the metric if it doesn't exist"""
        if name not in self.metrics:
            self.metrics[name] = cls(*args, **kwargs)
        return self.metrics[name]

    def __init__(self, config: Optional[Dict] = None):
        """Set up RtorrentExporter."""
        super().__init__(config)
        self.prefix = self.config.get("prefix", "rtorrent_")
        self.proxy = self.engine.open()

        self.active_jobs = set()
        jobs = ["item", "tracker", "system"]
        for j in self.config.get("jobs", "system").split(","):
            j = j.strip()
            if j not in jobs:
                self.log.warning("Job %s not found, skipping", j)
            else:
                self.active_jobs.add(j)
        self.metrics: Dict[str, Any] = {}

        # Create "constant" info metric
        self.info_methods = ["system.client_version", "system.library_version"]
        system_info = self.add_metric(
            "info", Info, self.prefix.rstrip("_"), "rTorrent platform information"
        )
        info_call = [dict(methodName=method, params=[]) for method in self.info_methods]
        info_results = [r[0] for r in self.proxy.system.multicall(info_call)]
        system_info.info(
            dict(zip([m.replace(".", "_") for m in self.info_methods], info_results))
        )

        # Set up some class variables that may not be used (depending
        # on configured jobs) for typing purposes
        self.system_stats: List[str] = []
        self.views: List[str] = []
        self.item_stats = sorted(
            set(self.config.get("item-stats", ["d.down.total", "d.up.total"]))
        )
        self.item_labels = sorted(
            set(self.config.get("item-labels", ["d.hash", "d.name"]))
        )
        self.add_metric(
            "scrape",
            PromCounter,
            self.prefix + "scrape",
            "Amount of scrapes against rTorrent",
        )
        self.add_metric(
            "last_scrape",
            Gauge,
            self.prefix + "last_scrape",
            "Timestamp of the last scrape time",
        )
        for j in self.active_jobs:
            getattr(self, f"init_{j}")()

        # Start the server
        # Taken from https://github.com/prometheus/client_python/blob/master/prometheus_client/exposition.py#L163
        port = int(self.config.get("port", 8000))
        addr = self.config.get("addr", "0.0.0.0")

        class TmpServer(exposition.ThreadingWSGIServer):
            """Copy of ThreadingWSGIServer to update address_family locally"""

        TmpServer.address_family, addr = exposition._get_best_family(addr, port)
        app = exposition.make_wsgi_app(REGISTRY)
        # Hold onto the server class so that we can shut it down during cleanup
        self.httpd = exposition.make_server(
            addr, port, app, TmpServer, handler_class=exposition._SilentHandler
        )
        t = Thread(target=self.httpd.serve_forever)
        t.daemon = True
        t.start()

    def init_item(self) -> None:
        """Initialize item metrics"""
        for s in self.item_stats:
            self.add_metric(
                s,
                Gauge,
                self.prefix + s.replace(".", "_"),
                f"rTorrent item stat {s}",
                [l.replace(".", "_") for l in self.item_labels],
            )

    def collect_item(self) -> None:
        """Collect item metrics"""
        call_list = self.item_stats + self.item_labels
        calls = [m + "=" for m in call_list]
        result = self.proxy.d.multicall2("", "main", *calls)
        for i in result:
            info = dict(list(zip(call_list, i)))
            for s in self.item_stats:
                self.metrics[s].labels(
                    **{k.replace(".", "_"): info[k] for k in self.item_labels}
                ).set(info[s])

    def init_tracker(self) -> None:
        """Initialize tracker metrics"""
        self.add_metric(
            "tracker_amount",
            Gauge,
            self.prefix + "tracker_amount",
            "Number of torrents belonging to a specific tracker",
            ["alias"],
        )
        self.add_metric(
            "tracker_errors",
            Gauge,
            self.prefix + "tracker_errors",
            "Number of torrents with tracker errors belonging to a specific tracker",
            ["alias"],
        )

    def collect_tracker(self) -> None:
        """Collect tracker metrics"""
        result = self.engine.items("main", ["d.custom=memo_alias", "d.message="])

        trackers = Counter([d.alias for d in result])
        tracker_errors = Counter([d.alias for d in result if d.message])

        for k, v in trackers.items():
            self.metrics["tracker_amount"].labels(alias=k).set(v)
            self.metrics["tracker_errors"].labels(alias=k).set(tracker_errors.get(k, 0))

    def init_system(self) -> None:
        """Initialize system metrics"""
        stat_methods = [
            "network.http.current_open",
            "network.http.max_open",
            "network.max_open_files",
            "network.max_open_sockets",
            "network.open_files",
            "network.open_sockets",
            "network.total_handshakes",
            "pieces.memory.block_count",
            "pieces.memory.current",
            "pieces.memory.max",
            "pieces.memory.sync_queue",
            "pieces.preload.min_rate",
            "pieces.preload.min_size",
            "pieces.preload.type",
            "pieces.stats.total_size",
            "pieces.stats_not_preloaded",
            "pieces.stats_preloaded",
            "pieces.sync.queue_size",
            "startup_time",
            "system.files.closed_counter",
            "system.files.failed_counter",
            "system.files.opened_counter",
            "throttle.global_down.max_rate",
            "throttle.global_down.rate",
            "throttle.global_down.total",
            "throttle.global_up.max_rate",
            "throttle.global_up.rate",
            "throttle.global_up.total",
            "throttle.max_downloads.global",
            "throttle.max_uploads.global",
            "throttle.unchoked_downloads",
            "throttle.unchoked_uploads",
        ]
        # Strip out unavailable methods
        self.system_stats = sorted(
            set(stat_methods) & set(self.proxy.system.listMethods())
        )
        # Set up metrics
        for name in self.system_stats:
            self.add_metric(
                name, Gauge, self.prefix + name.replace(".", "_"), f"rTorrent {name}"
            )
        self.add_metric(
            "view.size",
            Gauge,
            self.prefix + "view_size",
            "rTorrent view size",
            ["view"],
        )
        self.views = sorted(self.proxy.view.list())

    def collect_system(self) -> None:
        """Collect system metrics"""
        # Get data via multicall
        calls = [dict(methodName=method, params=[]) for method in self.system_stats] + [
            dict(methodName="view.size", params=["", view]) for view in self.views
        ]

        result = [r[0] for r in self.proxy.system.multicall(calls)]

        # Get numeric metrics
        for m in self.system_stats:
            self.metrics[m].set(result[0])
            del result[0]

        result = result[-len(self.views) :]

        # Get view information
        for v in self.views:
            self.metrics["view.size"].labels(view=v).set(result[0])
            del result[0]

    def run(self):
        """Trigger all configured active collectors"""
        for j in self.active_jobs:
            getattr(self, f"collect_{j}")()
        self.metrics["scrape"].inc()
        self.metrics["last_scrape"].set(time())

    def cleanup(self):
        """Clean up metrics from the global registry and shut down the
        server"""
        for metric in self.metrics.values():
            REGISTRY.unregister(metric)
        self.httpd.shutdown()
        self.httpd.server_close()


if __name__ == "__main__":
    from pyrosimple import connect

    engine = connect()

    job = RtorrentExporter({"jobs": "system", "port": 8005})
    while True:
        job.run()
        sleep(5)
