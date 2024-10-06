---
title: Changing announce URLs
---

# Changing announce URLs

Many solutions will have you use `sed` or some other core Linux
utility to do a find and replace.  While this usually works, it can
very easily cause corruption.


## Using `chtor`

This method requires rTorrent to be shut down first, but completely
removes the old announce:

```bash
# Shut down rTorrent
# Backing up the session directory is recommended: tar czvf rtorrent-session-$(date -Imin).tar.gz "$(rtxmlrpc session.path)"
cd "$(rtxmlrpc session.path)"
chtor --reannounce "https://example.com/announce/new" *.torrent --dry-run --diff # Dry-run the changes
chtor --reannounce "https://example.com/announce/new" *.torrent                  # Run for real
lstor  __hash__,announce *.torrent | grep example.com                            # Confirm the new URL is in place
# Start up rTorrent
```

!!! note
    By default, `--reannounce` will only change the torrent
    file if the current announce's domain or alias matches the new
    one.  If you use `--reannounce-all` to change all torrents, it
    will also change the `info.x_cross_seed` key, unless
    `--no-cross-seed` is also provided


## Using `rtcontrol`

The advantage of this method is that it doesn't require a restart of
rTorrent, but instead disables the old trackers and inserts the new
URL directly into the item:

```bash
rtcontrol "tracker=http://example.com/announce/old" \
  --exec 't.multicall=0,t.disable= ; d.tracker.insert=0,"https://example.com/announce/new" ; d.save_full_session='
rtcontrol "tracker=https://example.com/announce/new" # View torrents with the new announce
```
