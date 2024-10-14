from pyrosimple.torrent import engine


def _custom_fields():
    import socket

    from pyrosimple.torrent import engine
    from pyrosimple.util import fmt, matching

    # Add peer attributes not available by default
    def get_peer_data(obj, name, aggregator=None):
        "Get some peer data via a multicall."
        aggregator = aggregator or (lambda _: _)
        result = obj.rpc_call("p.multicall", ["", "p.%s=" % name])
        return aggregator([i[0] for i in result])

    yield engine.OnDemandField(
        int,
        "peers_connected",
        "number of connected peers",
        matcher=matching.FloatFilter,
        requires=["d.peers_connected"],
    )
    yield engine.DynamicField(
        set,
        "peers_ip",
        "list of IP addresses for connected peers",
        matcher=matching.TaggedAsFilter,
        formatter=", ".join,
        accessor=lambda o: set(get_peer_data(o, "address")),
        requires=["p.multicall=,p.address="],
    )
    yield engine.DynamicField(
        set,
        "peers_hostname",
        "list of hostnames for connected peers",
        matcher=matching.TaggedAsFilter,
        formatter=", ".join,
        accessor=lambda o: set(
            [socket.gethostbyaddr(i)[0] for i in get_peer_data(o, "address")]
        ),
        requires=["p.multicall=,p.address="],
    )
    yield engine.DynamicField(
        set,
        "peers_client",
        "Client/version for connected peers",
        matcher=matching.TaggedAsFilter,
        formatter=", ".join,
        accessor=lambda o: set(get_peer_data(o, "client_version")),
        requires=["p.multicall=,p.client_version="],
    )
    # Insert any other custom fields here


# Register our custom fields to the proxy
for field in _custom_fields():
    engine.TorrentProxy.add_field(field)
