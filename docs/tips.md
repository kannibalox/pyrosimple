---
title: Tips & Tricks
---

# Tip & Tricks

## Repairing Stuck Items

Sometimes items will get stuck in a state where they are unable to start correctly, even after a hash check. Check that rTorrent has the correct access to the file first, and if so this command will reset all the file states and force another hash check. This is the same as pressing `^K^E^R` in the UI.

```bash
rtcontrol --exec 'd.stop= ; d.close= ; f.multicall=,f.set_create_queued=0,f.set_resize_queued=0 ; d.check_hash=' \
  --from stopped // -/1 --yes
```

The above example only effect 1 torrent from the stopped view. After the hash check is complete and the torrent is working again, use `--start` to start it again.

## Working with ruTorrent

pyrosimple and ruTorrent can be used at the same time with no issue. To view/filter on ruTorrent's labels, use the `custom_1` field:

```bash
rtcontrol custom_1=TV -o alias,name
```

## Move data for selected items

This sequence will put all torrents for a specific tracker into a dedicated view,
then will stop them, move the data, set the directory, and restart them. The last
command then clears the view.

Note that if the items are not moved to the `d.directory.set` path, rTorrent
may start trying to download them again.

```bash
mkdir -p ~/rtorrent/data/TRK
rtcontrol --to-view=to-move alias=TRK realpath=$HOME/rtorrent/data
rtcontrol --from-view=to-move // --stop
rtcontrol --from-view=to-move // --spawn "mv {{item.path|shell}} $HOME/rtorrent/data/TRK" --exec "d.directory.set=$HOME/rtorrent/data/TRK" --flush
rtcontrol --from-view=to-move // --start
rtcontrol -M=to-move --alter=remove //
```

## Instance Statistics

```bash
#!/bin/bash
echo -n rTorrent $(rtxmlrpc system.client_version)/$(rtxmlrpc system.library_version)
echo -n , up $(rtxmlrpc -q convert.elapsed_time '' $(ls -l --time-style '+%s' $SCGI_SOCKET | awk '{print $6}'))
echo \ [$(rtcontrol -qo"1 {{d.uploaded}} {{d.size}}" \* | \
    awk '{ TOT += $1; UP += $2; SUM += $3} END { print TOT " loaded; U: " UP/1024/1024/1024 " GiB; S: " SUM/1024/1024/1024 }') GiB]

echo -n D: $(rtxmlrpc convert.xb '' $(rtxmlrpc throttle.global_down.total))
echo -n \ @ $(rtxmlrpc convert.xb '' $(rtxmlrpc throttle.global_down.rate))/s
echo -n \ of $(rtxmlrpc convert.xb '' $(rtxmlrpc throttle.global_down.max_rate))/s
echo -n , U: $(rtxmlrpc convert.xb '' $(rtxmlrpc throttle.global_up.total))
echo -n \ @ $(rtxmlrpc convert.xb '' $(rtxmlrpc throttle.global_up.rate))/s
echo -n \ of $(rtxmlrpc convert.xb '' $(rtxmlrpc throttle.global_up.max_rate))/s
echo
```

Note that this can also be implemented much more efficiently as a python script:
```python
#!/usr/bin/env python3
import pyrosimple

engine = pyrosimple.connect()
proxy = engine.open()

print(f"rTorrent {proxy.system.client_version()}/{proxy.system.library_version()}", end='')
print(f", up {proxy.convert.elapsed_time('', str(proxy.startup_time()))}", end='')
count = 0
size = 0
uploaded = 0
for item in engine.view():
    count += 1
    size += item.size
    uploaded += item.uploaded
print(f"[TOT {count}; U: {proxy.convert.xb('', str(uploaded))}; S {proxy.convert.xb('', str(size))}]")
print(f"D: {proxy.convert.xb('', str(proxy.throttle.global_down.total()))} ", end='')
print(f"@ {proxy.convert.xb('', str(proxy.throttle.global_down.rate()))}/s ", end='')
print(f"of {proxy.convert.xb('', str(proxy.throttle.global_down.max_rate()))}/s, ", end='')
print(f"U: {proxy.convert.xb('', str(proxy.throttle.global_up.total()))} ", end='')
print(f"@ {proxy.convert.xb('', str(proxy.throttle.global_up.rate()))}/s ", end='')
print(f"of {proxy.convert.xb('', str(proxy.throttle.global_up.max_rate()))}/s")
```

## Find orphaned files

Since Jinja2 is more sandboxes than the original Tempita templating system, the `orphans.txt` template file from pyrocore no longer works. However, we can replicate the functionality with a little fancy scripting. The following command will list the orphan files along with their sizes:
```bash
target_dir=/mnt/test
comm -13 \
  <(rtcontrol -o filelist "path=${target_dir}*" | sort) \
  <(find "$target_dir" -type f | sort) \
  | tr '\n' '\0' | xargs -0 du -hsc
```

To clean up the files (after ensuring the list is accurate!), we can just change the final command from `du` to `rm`. Note that this example uses `echo rm` to ensure nothing is deleted accidentally:

```bash
comm -13 \
  <(rtcontrol -o filelist "path=${target_dir}*" | sort) \
  <(find "$target_dir" -type f | sort) \
  | tr '\n' '\0' | xargs -0 echo rm
```
