---
title: Custom Code
---

# Custom Code

`pyrosimple` offers a couple ways to extend its functionality if you
know a little Python.

## Custom fields

The ``config.py`` script can be used to add custom logic to your
setup. The most common use for this file is adding custom fields.

To add user-defined fields you can put code describing them into your
``~/.config/pyrosimple/config.py`` file. You can then use your custom
field just like any built-in one, e.g. issue a command like
``rtcontrol --from-view incomplete \* -qco partial_done,name`` (see
below examples). They're also listed when you call ``rtcontrol
--help-fields``.

Here's an example of adding a simple custom field:

```python
from pyrosimple.torrent import engine
def _custom_fields():
    from pyrosimple.torrent import engine
    from pyrosimple.util import fmt, matching

    # Add a single field, which is matched like a number,
    # and accessed by performing a single RPC call.
    yield engine.ConstantField(
        int,
        "piece_size", # name of the field
        "Piece size for the item", # The description for --help
        matcher=matching.FloatFilter, # The type to use when matching the field
        accessor=lambda o: o.rpc_call("d.size_chunks"), # How to actually access the method
        requires=["d.size_chunks"], # Optional but speeds up the process
    )

    # Insert any other custom fields here

# Register our custom fields to the proxy
for field in _custom_fields():
    engine.TorrentProxy.add_field(field)
```
```bash
rtcontrol // -o piece_size
```

You can see how the built-in fields are defined in
[torrent/engine.py](https://github.com/kannibalox/pyrosimple/blob/main/src/pyrosimple/torrent/engine.py)
if you want to see more complete examples.

### Examples

#### Tracker info

```python
    # Add tracker attributes not available by default
    def get_tracker_field(obj, name, aggregator=sum):
        "Get an aggregated tracker field."
        return aggregator(obj.rpc_call("t.multicall", ["", f"t.{name}="])[0])
    yield engine.DynamicField(
        int,
        "downloaders",
        "number of completed downloads",
        matcher=matching.FloatFilter,
        accessor=lambda o: get_tracker_field(o, "scrape_downloaded"),
    )
    yield engine.DynamicField(
        int,
        "seeds",
        "number of seeds",
        matcher=matching.FloatFilter,
        accessor=lambda o: get_tracker_field(o, "scrape_complete"),
        requires=['t.multicall=,t.scrape_complete=']
    )
    yield engine.DynamicField(
        int,
        "leeches",
        "number of leeches",
        matcher=matching.FloatFilter,
        accessor=lambda o: get_tracker_field(o, "scrape_incomplete"),
    )
```

### Peer Information

```python
    # Add peer attributes not available by default
    def get_peer_data(obj, name, aggregator=None):
        "Get some peer data via a multicall."
        aggregator = aggregator or (lambda _: _)
        result = obj._engine._rpc.p.multicall(obj._fields["hash"], "", "p.%s=" % name)
        return aggregator([i[0] for i in result])
    yield engine.DynamicField(
        set,
        "peers_ip",
        "list of IP addresses for connected peers",
        matcher=matching.TaggedAsFilter,
        formatter="\n".join,
        accessor=lambda o: set(get_peer_data(o, "address")),
    )

    yield engine.DynamicField(
        set,
        "peers_hostname",
        "list of hostnames for connected peers",
        matcher=matching.TaggedAsFilter,
        formatter="\n".join,
        accessor=lambda o: set(
            [socket.getfqdn(p) for p in get_peer_data(o, "address")]
        ),
    )
```

## As a library

The main interface has been designed to be deliberately simple if you
wish to connect to rtorrent from within another Python program:

```python
import pyrosimple
engine = pyrosimple.connect()
proxy = engine.open()
```

With this setup, `engine` can provide the same kind of high-level
views and abstractions seen in `rtcontrol`:

```python
engine.log("Hello world!") # Prints to console of rtorrent
print(list(engine.view("incomplete")))
```

While `proxy` allows for low-level direct RPC calls, just like
`rtxmlrpc`:

```python
print(proxy.system.hostname())
print(proxy.d.multicall2('', 'main', 'd.hash='))
```

If you want to skip the auto-detection of rtorrent's URL, simply pass
in your own to `connect()`:

```python
engine = pyrosimple.connect("scgi://localhost:9000")
```

See the
[`examples`](https://github.com/kannibalox/pyrosimple/tree/main/docs/examples)
directory for some useful python scripts.
