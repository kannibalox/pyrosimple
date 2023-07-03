---
title: General maintenance tasks
---

This is just to meant to be a section for useful commands that may not
merit a full page.

### Dumping items as a JSON array

If you want to access rTorrent item data in a machine readable form,
you can feed the output of `rtcontrol` with the `--json` option into
another script for further processing. By using `-o/--output`, you can
also filter the fields being output. The following examples use the
[`jq`](https://stedolan.github.io/jq/tutorial/) utility to validate
and re-print the JSON data.

```bash
# Process all known fields of the first torrent through jq
rtcontrol --select 1 // | jq .
# Process only the name and size
rtcontrol -o name,size --select 1 // | jq .
```

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

This is best done before taking any backups, and after making any big
changes. Note that by default `session.save` is run on 20 minutes schedule.

### Move data for selected items to a new location

This sequence of commands will stop the selected items, move their
data, flush rTorrent’s metadata (session state), and finally starts
everything again, followed by removing the items from the tagged
view. The order matters and cannot be changed.

```
mkdir -p ~/rtorrent/data/TRK
rtcontrol --to-view=trk-to-move alias=TRK realpath=$HOME/rtorrent/data is_complete=yes
rtcontrol --from-view=trk-to-move // --yes \
  --stop \
  --spawn "mv {{item.path}} $HOME/rtorrent/data/TRK" \
  --exec "directory.set=$HOME/rtorrent/data/TRK" \
  --flush \
  --start
rtcontrol --modify-view=trk-to-move --alter=remove realpath=$HOME/rtorrent/data/TRK
```

By changing the first `rtcontrol` command that populates the tagged
view, you can change this to move data for
[any criteria](usage-rtcontrol.md#filter-conditions) you can think of.

## Using tags to control item processing

By using the `--tag` command, it becomes easy to write scripts that will only run once against each item:

```bash
#!/usr/bin/env bash
guard="handled"
rtcontrol --from-view=complete -q -o hash "tagged=!$guard" | \
while read hash; do
    # Do any processing
    rtxmlrpc d.hash "$hash"
    # Mark item as handled
    rtcontrol -q "hash=$hash" // --tag "$guard" --flush --yes
done
```
