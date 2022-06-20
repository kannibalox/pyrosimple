---
title: Experimental Features
---

# Experimental Features

## Connecting to multiple clients

!!! warning

    This can cause strange behavior unless planned out. As an example, hashes are no longer enough to uniquely identify a torrent.

`rtxmlrpc` and `rtcontrol` support talking to multiple clients, by specifying a TOML list
in the `CONNECTIONS` section:
```toml
[CONNECTIONS]
local="localhost:7000"
seedbox="seedbox.example.com:7000"
all=["local","seedbox"]
```
```bash
rtxmlrpc -U all system.hostname
```

## Connecting over SSH

!!! Requirements

    `socat` is required to be installed on the remote server for this functionality.

```bash
# Via port
rtxmlrpc -U scgi+ssh://example.com/TCP:0.0.0.0:7000 system.hostname
# Via domain socket
rtxmlrpc -U scgi+ssh://example.com/UNIX-CONNECT:/home/rtorrentr/scgi.sock system.hostname
```

Since each command opens a new SSH connection, setting up the ControlPersist feature in
`~/.ssh/config` is highly recommended.

Examples:
```
Host *
  ControlMaster auto
  ControlPath ~/.ssh/sockets/%r@%h-%p
  ControlPersist 600
```
