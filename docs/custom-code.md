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

```python title="config.py"
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

### Examples

You can see how the built-in fields are defined in
[torrent/engine.py](https://github.com/kannibalox/pyrosimple/blob/main/src/pyrosimple/torrent/engine.py)
if you want to see more complete examples.

#### Tracker info

These allow you to see the number of downloaders, seeders and leechers
on items, provided the tracker supports [announce
scrapes](https://wiki.theory.org/BitTorrentSpecification#Tracker_.27scrape.27_Convention).

By default rTorrent only does a single scrape on restart or when an
item is first added, which is why these fields aren't available by
default. You'll need to set up your configuration as described in the
[rTorrent github
wiki](https://github.com/rakshasa/rtorrent/wiki/Auto-Scraping) in
order to see up-to-date values for these fields.

```python
{% include 'examples/custom-fields-trackers.py' %}
```

#### Peer Information

Note that due to requiring a DNS lookup, `peers_hostname` may take a
long time to display.

```python
{% include 'examples/custom-fields-peers.py' %}
```

#### Checking for specific files

```python
{% include 'examples/custom-fields-files.py' %}
```

#### Partial Downloads

Note that the `partial_done` value can be a little lower than it
actually should be, when chunks shared by different files are not yet
complete; but it will eventually reach `100` when all selected chunks
are downloaded in full.

```python
{% include 'examples/custom-fields-partial.py' %}
```

#### Checking disk space

This custom field also introduces the concept of using custom settings
from `config.toml`. The code below uses `diskspace_threshold_mb` to
decide if there's enough extra space on the disk (in addition to the
amount the torrent uses) to consider it valid. If that setting isn't
defined, it defaults to `500`.

This field is particularly powerful when combined with the
[QueueManager](pyrotorque-jobs.md#queue-manager), to prevent it from
accidentally filling up a disk.

```python
{% include 'examples/custom-fields-disk-space.py' %}
```

#### ruTorrent

Some [ruTorrent](https://github.com/Novik/ruTorrent) plugins add additional custom fields:
```py
from pyrosimple.torrent import engine

def _custom_rutorrent_fields():
    from pyrosimple.torrent import engine
    yield engine.DynamicField(
        int,
        "ru_seedingtime",
        "total seeding time after completion (ruTorrent variant)",
        matcher=matching.DurationFilter,
        accessor=lambda	o: int(o.rpc_call("d.custom",["seedingtime"]) or "0")/1000,
        formatter=engine._fmt_duration,
        requires=["d.custom=seedingtime"]
    )
    yield engine.DynamicField(
        int,
        "ru_addtime",
        "date added (ruTorrent variant)",
        matcher=matching.DurationFilter,
        accessor=lambda o: int(o.rpc_call("d.custom",["addtime"]) or "0")/1000,
        formatter=engine._fmt_duration,
        requires=["d.custom=addtime"]
    )

for field in _custom_rutorrent_fields():
    engine.TorrentProxy.add_field(field)
```

## As a library

The main interface has been designed to be deliberately simple if you
wish to connect to rtorrent from within another Python program.

```python
import pyrosimple
engine = pyrosimple.connect()
proxy = engine.open()
```

With this setup, `engine` can provide the same kind of high-level
views and abstractions seen in `rtcontrol`.

```python
engine.log("Hello world!") # Prints to console of rtorrent
print([item.done for item in engine.view("incomplete")]) # List the done percentage for torrents in the incomplete view
```

While `proxy` allows for low-level direct RPC calls, just like
`rtxmlrpc`.

```python
print(proxy.system.hostname())
print(proxy.d.multicall2('', 'main', 'd.hash='))
```

If you want to skip the auto-detection of rtorrent's URL, simply pass
in your own to `connect()`.

```python
engine = pyrosimple.connect("scgi://localhost:9000")
```

See the
[`examples`](https://github.com/kannibalox/pyrosimple/tree/main/docs/examples)
directory for some useful python scripts.
