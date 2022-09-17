---
title: rTorrent configuration
---

While no rTorrent configuration is strictly required, some fields will
only work correctly with configuration, and commands can be assigned
for easy access.

# Fields

## Timestamps
These events record timestamps for `loaded`, `started`, and `completed`.
```toml
method.insert = pyro._tm_started.now, simple|private,\
    "d.custom.set=tm_started,$cat=$system.time= ; d.save_resume="
method.insert = pyro._tm_completed.now, simple|private,\
    "d.custom.set=tm_completed,$cat=$system.time= ; d.save_resume="

method.set_key = event.download.resumed, !time_stamp,\
    "branch=d.custom=tm_started,false=,pyro._tm_started.now="
method.set_key = event.download.inserted_new, !time_stamp,\
    "d.custom.set=tm_loaded,$cat=$system.time= ; d.save_resume="
method.set_key = event.download.finished, !time_stamp,\
    "pyro._tm_completed.now="
method.set_key = event.download.hash_done, !time_stamp,\
    "branch=\"and={d.complete=,not=$d.custom=tm_completed}\", pyro._tm_completed.now="
```

The following command can be used to backfill the data where possible:
```bash
# Remove the --dry-run to actually backfill the data.
pyroadmin backfill --dry-run
```
This is safe to run multiple times if needed.

# UI

## Searching

The following snippet allows for quick searching directly in the
UI. The examples below can be modified to suit any searches you find
yourself using often.

```toml
# VIEW: Use rtcontrol filter (^X s=KEYWORD, ^X t=TRACKER, ^X f="FILTER")
method.insert = s,simple|private,"execute.nothrow=rtcontrol,--detach,-qV,\"$cat=*,$argument.0=,*\""
method.insert = t,simple|private,"execute.nothrow=rtcontrol,--detach,-qV,\"$cat=\\\"alias=\\\",$argument.0=\""
method.insert = f,simple|private,"execute.nothrow=rtcontrol,--detach,-qV,$argument.0="
```
