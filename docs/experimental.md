---
title: Experimental Features
---

# Experimental Features

## Query optimization

!!! Requirements

    *rTorrent* must support the `d.multicall.filtered` method, which requires vanilla version 0.9.8+,
    or rTorrent-PS 1.1+.

If your rTorrent supports `d.multicall.filtered`, rtcontrol can take
advantage of it to return results faster. The option is controlled by
the `-Q` flag in rtcontrol, or `fast_query` in the configuration file.

Level `1` is less aggressive and safe by definition (i.e. produces
correct results in all cases, unless there's a bug), while ``-Q2`` is
highly experimental and in some circumstances likely produces results
that are too small or empty.

Optimization works by giving a pre-filter condition to rTorrent,
to reduce the overhead involved in sending items over XMLRPC and
processing them, only to be then discarded in the ``rtcontrol`` filter
machinery.

This goal of reducing the number of items sent to ``rtcontrol`` is
best achieved if you put a highly selective condition first in a
series of conditions. For cron-type jobs, this can often be achieved
by looking at recent items only – older items should already be
processed by previous runs. Even a very lenient window like “last
week” drastically reduces items that need to be processed.

```bash
$ rtcontrol loaded=-6w is_ignored=0 -o- -v -Q0
DEBUG:pyrosimple.util.rpc:method 'd.multicall2', params ('', 'default', 'd.custom=tm_loaded', 'd.hash=', 'd.ignore_commands=', 'd.name=')
DEBUG:pyrosimple.torrent.rtorrent.RtorrentEngine:Got 23771 items with 4 attributes from 'localhost:415' [<xmlrpc.client._Method object at 0x7ff59c348d30>]
DEBUG:pyrosimple.util.rpc:method 'view.size', params ('', 'default')
INFO:pyrosimple.scripts.rtcontrol.RtorrentControl:Filtered 627 out of 23771 torrents.
DEBUG:pyrosimple.scripts.rtcontrol.RtorrentControl:RPC stats: <RTorrentProxy via json for scgi://localhost:7000?rpc=json>
INFO:pyrosimple.scripts.rtcontrol.RtorrentControl:Total time: 1.404 seconds.
$ rtcontrol loaded=-6w is_ignored=0 -o- -v -Q1
INFO:pyrosimple.torrent.rtorrent.RtorrentEngine:!!! pre-filter: greater=value=$d.custom=tm_loaded,value=1652724506
DEBUG:pyrosimple.util.rpc:method 'd.multicall.filtered', params ('', 'default', 'greater=value=$d.custom=tm_loaded,value=1652724506', 'd.custom=tm_loaded', 'd.hash=', 'd.ignore_commands=', 'd.name=')
DEBUG:pyrosimple.torrent.rtorrent.RtorrentEngine:Got 636 items with 4 attributes from 'localhost:415' [<xmlrpc.client._Method object at 0x7f7f03428dc0>]
DEBUG:pyrosimple.util.rpc:method 'view.size', params ('', 'default')
INFO:pyrosimple.scripts.rtcontrol.RtorrentControl:Filtered 627 out of 23771 torrents.
DEBUG:pyrosimple.scripts.rtcontrol.RtorrentControl:RPC stats: <RTorrentProxy via json for scgi://localhost:7000?rpc=json>
INFO:pyrosimple.scripts.rtcontrol.RtorrentControl:Total time: 0.672 seconds.
```

## Connecting to multiple clients

!!! warning

    This can cause strange behavior unless planned out. For instance, hashes are no longer enough to uniquely identify a torrent.

`rtxmlrpc` and `rtcontrol` support talking to multiple clients, by specifying a TOML list
in the `CONNECTIONS` section:
```toml
[CONNECTIONS]
local="localhost:7000"
remote="remote.example.com:7000"
seedbox="https://username:password@seedbox.example.com"
all=["local","seedbox","remote"]
```
```bash
rtxmlrpc -U all system.hostname
```

## Connecting over SSH

!!! Requirements

    `socat` is required to be installed on the remote server for this functionality.
    SSH authentication must also happen without any prompts, (i.e. through `authorized_keys`
    or a SSH agent that holds your password)

```bash
# Via port
rtxmlrpc -U scgi+ssh://example.com/TCP:0.0.0.0:7000 system.hostname
# Via domain socket
rtxmlrpc -U scgi+ssh://example.com/UNIX-CONNECT:/home/rtorrent/scgi.sock system.hostname
```

Since each command opens a new SSH connection, setting up the
ControlPersist feature in `~/.ssh/config` is highly recommended.

Example:
```
Host *
  ControlMaster auto
  ControlPath ~/.ssh/sockets/%r@%h-%p
  ControlPersist 600
```
