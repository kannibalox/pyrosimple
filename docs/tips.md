---
title: Tips & Tricks
---

# Tip & Tricks

## Working with ruTorrent

pyrosimple and ruTorrent can be used at the same time with no
issue. To view/filter on ruTorrent's labels, use the `custom_1` field:

```bash
rtcontrol custom_1=TV -o alias,name
```

For convience, the same value is available under the `label` field:

```bash
rtcontrol label=TV -o alias,name
```

## Repairing stuck items

Sometimes items will get stuck in a state where they are unable to
start correctly, even after a hash check. Check that rTorrent has the
correct access to the file first, and if so this command will reset
all the file states and force another hash check. This is the same as
pressing `^K^E^R` in the UI.

```bash
rtcontrol --exec 'd.stop= ; d.close= ; f.multicall=,f.set_create_queued=0,f.set_resize_queued=0 ; d.check_hash=' \
  --from stopped // -/1 --yes
```

The above example only effect 1 torrent from the stopped view. After
the hash check is complete and the torrent is working again, use
`--start` to start it again.

## Instance statistics

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

Since Jinja2 is more
[sandboxed](https://jinja.palletsprojects.com/en/3.1.x/sandbox/) than
the original Tempita templating system, the `orphans.txt` template
file from pyrocore no longer works. However, we can replicate the
functionality with a little fancy scripting. The following command
will list the orphan files along with their sizes:

```bash
target_dir=/mnt/test
comm -13 \
  <(rtcontrol -o filelist "path=${target_dir}*" | sort) \
  <(find "$target_dir" -type f | sort) \
  | tr '\n' '\0' | xargs -0 du -hsc
```

To clean up the files (after ensuring the list is accurate!), we can
just change the final command from `du` to `rm`. Note that this
example uses `echo rm` to ensure nothing is deleted accidentally:

```bash
comm -13 \
  <(rtcontrol -o filelist "path=${target_dir}*" | sort) \
  <(find "$target_dir" -type f | sort) \
  | tr '\n' '\0' | xargs -0 echo rm
```

## Dumping items as a JSON array

If you want to access rTorrent item data in machine readable form via rtcontrol, you can use its --json option and feed the output into another script parsing the JSON data for further processing.

Here’s an example:

```
$ rtcontrol --json -qo name,is_ghost,directory,fno ubuntu-22.04.iso
[
  {
    "directory": "/var/torrent/load/foo",
    "fno": 1,
    "is_ghost": false,
    "name": "ubuntu-22.04.iso"
  }
]
```

rtxmlrpc is also capable of producing JSON output:
```
$ rtxmlrpc -o json d.multicall2 '' main d.name= d.directory= d.size_files=
[["ubuntu-22.04.iso", "/var/torrent/load/foo", 1]]
```
