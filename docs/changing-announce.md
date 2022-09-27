---
title: Changing announce URLs
---

# Changing announce URLs

Many solutions will have you use `sed` or some other core Linux
utility to do a find and replace.  While this usually works, it can
very easily cause corruption.

## Using `rtcontrol`

The advantage of this method is that it doesn't require a restart of
rTorrent, but instead disables the old trackers and inserts the new
URL directly into the item:

```bash
rcontrol "tracker=http://example.com/announce/old" \
  --exec 't.multicall=0,t.disable= ; d.tracker.insert=0,"http://example.com/announce/new" ; d.save_full_session='
```

## Using `chtor`

This method is more intrusive and requires rTorrent to be shut down
first, but is cleaner in that the old URL is completely removed

```bash
# Shut down rTorrent
# Backing up the session directory is recommended: tar czvf rtorrent-session-$(date -Imin).tar.gz "$(rtxmlrpc session.path)"
cd "$(rtxmlrpc session.path)"
chtor --reannounce "http://example.com/announce/new" *.torrent
# Start up rTorrent
```
