"""Jobs for metric reporting"""
import threading

from collections import Counter
from time import sleep

from prometheus_client import start_http_server
from prometheus_client.core import REGISTRY, GaugeMetricFamily

from pyrosimple import config as config_ini
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


class ClientServer(threading.Thread):
    """Simple thread class to run the prometheus HTTP server
    in the background"""

    def __init__(self, port):
        super().__init__()
        self.port = int(port)

    def run(self):
        start_http_server(self.port)


class RtorrentCollector:
    """Base class for all the different collectors"""

    def __init__(self, proxy, config):
        self.proxy = proxy
        self.config = config
        self.prefix = self.config.get("prefix", "rtorrent_")

    def collect(self):
        """Must be implemented by the child classes"""
        raise NotImplementedError


class RtorrentItemCollector(RtorrentCollector):
    """Collects per-item information
    This will most likely caush prometheus to burn except with smaller instances"""

    def __init__(self, proxy, config):
        super().__init__(proxy, config)

        available_methods = set(self.proxy.system.listMethods())
        self.item_stat_methods = set(
            self.config.get("item-stats", ["d.down.total", "d.up.total"])
        )
        self.item_labels = set(self.config.get("item-labels", ["d.hash", "d.name"]))
        # Strip out unavailable methods
        self.item_stat_methods &= available_methods
        self.item_labels &= available_methods

    def collect(self):
        calls = [
            "d." + m + "=" for m in list(self.item_stat_methods) + self.item_labels
        ]
        result = self.proxy.d.multicall2("", "main", *calls)
        item_stats = {}
        for stat in self.item_stat_methods:
            item_stats[stat] = GaugeMetricFamily(
                self.prefix + stat.replace(".", "_"), stat, labels=self.item_labels
            )
        for i in result:
            info = dict(list(zip(list(self.item_stat_methods) + self.item_labels, i)))
            for stat, gauge in item_stats.items():
                gauge.add_metric([info[l] for l in self.item_labels], info[stat])
        for stat, guage in item_stats.items():
            yield guage


class RtorrentTrackerCollector(RtorrentCollector):
    """Collects tracker-based summaries"""

    def collect(self):
        tracker_gauge = GaugeMetricFamily(
            self.prefix + "tracker_amount",
            "Number of torrents belonging to a specific tracker",
            labels=["alias"],
        )
        tracker_error_gauge = GaugeMetricFamily(
            self.prefix + "tracker_errors",
            "Number of torrents with tracker errors belonging to a specific tracker",
            labels=["alias"],
        )

        item_fields = ["d.tracker_domain=", "d.message="]
        result = self.proxy.d.multicall2("", "main", *item_fields)

        trackers = Counter([config_ini.map_announce2alias(d[0]) for d in result])
        tracker_errors = Counter(
            [config_ini.map_announce2alias(d[0]) for d in result if d[1]]
        )

        for k, v in trackers.items():
            tracker_gauge.add_metric([k], v)
        for (
            k
        ) in (
            trackers.keys()
        ):  # Use the "trackers" keys to make sure all active trackers get a value
            tracker_error_gauge.add_metric([k], tracker_errors[k])

        yield tracker_gauge
        yield tracker_error_gauge


class RtorrentSystemCollector(RtorrentCollector):
    """Collects system information. This is both the most useful and least
    impactful collector, as it only takes a single system.multicall to collect
    all the information"""

    def __init__(self, proxy, config):
        super().__init__(proxy, config)
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

        self.info_methods = ["system.client_version", "system.library_version"]

        # Strip out unavailable methods
        self.system_stats = set(stat_methods) & set(self.proxy.system.listMethods())

    def collect(self):
        system_info = GaugeMetricFamily(
            self.prefix + "info",
            "rTorrent platform information",
            labels=[m.replace(".", "_") for m in self.info_methods],
        )
        system_view_size = GaugeMetricFamily(
            self.prefix + "view_size", "Size of rtorrent views", labels=["view"]
        )
        views = self.proxy.view.list()

        # Get data via multicall
        calls = (
            [dict(methodName=method, params=[]) for method in sorted(self.system_stats)]
            + [dict(methodName=method, params=[]) for method in self.info_methods]
            + [dict(methodName="view.size", params=["", view]) for view in views]
        )

        result = [r[0] for r in self.proxy.system.multicall(calls)]

        # Get numeric metrics
        for m in sorted(self.system_stats):
            yield GaugeMetricFamily(
                self.prefix + m.replace(".", "_"), m, value=result[0]
            )
            del result[0]

        # Get text-like information
        system_info.add_metric(result[0 : len(result) - len(views)], 1)
        yield system_info
        result = result[-len(views) :]

        # Get view information
        for v in views:
            system_view_size.add_metric([v], result[0])
            del result[0]
        yield system_view_size


class RtorrentExporter(BaseJob):
    """Expose rTorrent and host statistics for scraping by a Prometheus instance."""

    def __init__(self, config=None):
        """Set up RtorrentExporter."""
        super().__init__(config)
        self.prefix = self.config.get("prefix", "rtorrent_")
        self.proxy = self.engine.open()
        jobs = {
            "item": RtorrentItemCollector,
            "tracker": RtorrentTrackerCollector,
            "system": RtorrentSystemCollector,
        }
        for j in self.config.get("jobs", "system").split(","):
            j = j.strip()
            if j not in jobs:
                self.log.error("Job %s not found, skipping", j)
            else:
                REGISTRY.register(jobs[j](self.proxy, self.config))

        # Start the server right off the bat
        self.prom_thread = ClientServer(self.config.get("port", "8000"))
        self.prom_thread.start()

    def run(self):
        # NOOP, stats are generated at scrape time
        pass


if __name__ == "__main__":
    from pyrosimple import connect

    engine = connect()

    job = RtorrentExporter({"jobs": "system", "port": 8005})
    while True:
        job.run()
        sleep(5)
