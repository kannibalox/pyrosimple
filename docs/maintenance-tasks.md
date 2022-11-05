---
title: General maintenance tasks
---

This is just to meant to be a section for useful commands that may not merit a full page.

### Flush all session data to disk

The
[`session.save`](https://rtorrent-docs.readthedocs.io/en/latest/cmd-ref.html#term-session-save)
command saves the changing parts of the session status, that is the
`*.torrent.libtorrent_resume` and `*.torrent.rtorrent files.` The copy
of the original `*.torrent` metafile never changes and is thus left
untouched.

If you want to flush all the session data, call rtxmlrpc as follows:

```
rtxmlrpc session.save
```

This is best done before taking any backups, and after making any big changes.

### Move data for selected items to a new location

This sequence of commands will stop the selected items, move their data, adapt rTorrent’s metadata (session state), and finally starts everything again, followed by removing the items from the tagged view. The order matters and cannot be changed.

```
mkdir -p ~/rtorrent/data/TRK
rtcontrol --to-view trk-to-move alias=TRK realpath=$HOME/rtorrent/data is_complete=yes
rtcontrol --from-view trk-to-move // --yes \
  --stop \
  --spawn "mv {{item.path}} $HOME/rtorrent/data/TRK" \
  --exec "directory.set=$HOME/rtorrent/data/TRK" \
  --flush
rtcontrol -M trk-to-move --alter=remove realpath=$HOME/rtorrent/data/TRK
```
By changing the first `rtcontrol` command that populates the tagged view, you can change this to move data for any [criteria](usage-rtcontrol.md#filter-conditions) you can think of.

## Using tags to control item processing

By using the `--tag` command, it becomes easy to write scripts that will only run once against each item:

```
#! /usr/bin/env bash
guard="handled"
rtcontrol --from-view complete -qohash tagged=\!$guard | \
while read hash; do
    # Do any processing
    rtxmlrpc d.hash "$hash"
    # Mark item as handled
    rtcontrol -q "hash=$hash" // --tag "$guard" --flush --yes
done
```
