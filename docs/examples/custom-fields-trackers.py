from pyrosimple.torrent import engine


def _custom_fields():
    from pyrosimple.torrent import engine
    from pyrosimple.util import fmt, matching

    def get_tracker_field(obj, name, aggregator=sum):
        "Get an aggregated tracker field."
        return aggregator(
            [t[0] for t in obj.rpc_call("t.multicall", ["", f"t.{name}="])]
        )

    yield engine.DynamicField(
        int,
        "downloaders",
        "number of completed downloads",
        matcher=matching.FloatFilter,
        accessor=lambda o: get_tracker_field(o, "scrape_downloaded"),
        requires=["t.multicall=,t.scrape_downloaded="],
    )
    yield engine.DynamicField(
        int,
        "seeds",
        "number of seeds",
        matcher=matching.FloatFilter,
        accessor=lambda o: get_tracker_field(o, "scrape_complete"),
        requires=["t.multicall=,t.scrape_complete="],
    )
    yield engine.DynamicField(
        int,
        "leeches",
        "number of leeches",
        matcher=matching.FloatFilter,
        accessor=lambda o: get_tracker_field(o, "scrape_incomplete"),
        requires=["t.multicall=,t.scrape_incomplete="],
    )
    yield engine.DynamicField(
        engine.untyped,
        "lastscraped",
        "time of last scrape",
        matcher=matching.TimeFilter,
        accessor=lambda o: get_tracker_field(o, "scrape_time_last", max),
        formatter=lambda dt: fmt.human_duration(float(dt), precision=2, short=True),
        requires=["t.multicall=,t.scrape_time_last="],
    )


# Register our custom fields to the proxy
for field in _custom_fields():
    engine.TorrentProxy.add_field(field)
