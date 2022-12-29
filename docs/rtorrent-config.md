---
title: rTorrent configuration
---

# rTorrent configuration

While no rTorrent configuration is strictly required, some fields will
only work correctly with configuration, and commands can be assigned
to rTorrent functions for easy access.

!!! tip
    To quickly generate a full config, run the following command:
    ```
    pyroadmin --create-rtorrent-rc
    ```

The full-featured `rtorrent.rc` referenced above is provided
[here](https://github.com/kannibalox/pyrosimple/raw/main/src/pyrosimple/data/full-example.rc). The
configuration [provided by
pyrocore](https://github.com/pyroscope/pyrocore/tree/master/src/pyrocore/data/config/rtorrent.d)
should still be compatible as well.

## rTorrent installation

Any version of rTorrent >=0.9.6 is supported, however the efficiency
improvements and JSON-RPC support that have been added to
[jesec/rtorrent](https://github.com/jesec/rtorrent) make it highly
recommended. If you prefer a nice UI (among other quality-of-life
fixes), consider
[rTorrent-PS](https://github.com/pyroscope/rtorrent-ps) as well.

## Fields

### Timestamps

These events record timestamps for `loaded`, `started`, and `completed`.
```toml
{% include 'examples/timestamps.rc' %}
```

The following command can be used to backfill the data where possible:
```bash
# Remove the --dry-run to actually backfill the data.
pyroadmin backfill --dry-run
```
This is safe to run multiple times if needed.

## UI

### Searching

The following snippet allows for quick searching directly in the
UI. The examples below can be modified to suit any searches you find
yourself using often.

```toml
# VIEW: Use rtcontrol filter (^X s=KEYWORD, ^X t=TRACKER, ^X f="FILTER")
method.insert = s,simple|private,"execute.nothrow=rtcontrol,--detach,-qV,\"$cat=*,$argument.0=,*\""
method.insert = t,simple|private,"execute.nothrow=rtcontrol,--detach,-qV,\"$cat=\\\"alias=\\\",$argument.0=\""
method.insert = f,simple|private,"execute.nothrow=rtcontrol,--detach,-qV,$argument.0="
```
