---
title: rtxmlrpc Usage
---

# rtxmlrpc

Since rtxmlrpc is intended to interact directly with rTorrent, it is deliberately designed to be simple. However, there are a few useful features to be aware of.

## Typing

Most of the time, strings are sufficient for dealing with rTorrent's commands, however sometimes you may need to coerce arguments
to be a certain type.
Start arguments with `+` or `-` to indicate they're numbers (type i4 or i8).
Use `[1,2,...` for arrays. Use `@` to indicate binary data, which can be
followed by a file path (e.g. `@/path/to/file`), a URL (https, http, ftp,
and file are supported), or `@-` to read from stdin.

!!! Note
    Using the `@` syntax to load data from URLs requires the `requests` library to be installed:
    ```
    pip install requests
    ```

Examples:
```bash
# Force an integer
rtxmlrpc throttle.max_downloads.div.set '' +100
# Load data from stdin
echo 'Hello world!' | rtxmlrpc print '' @-
# Load binary data from a URL
rtxmlrpc load.raw '' @https://releases.ubuntu.com/22.04/ubuntu-22.04-live-server-amd64.iso.torrent
```

# Running as import

It's also possible to run commands directly through rTorrent's command system, through the use of its `import` command.
By specifying the `-i`/`--as-import` flag, rtxmlrpc will write the command to a temporary file, and tell rTorrent to `import` it directly.

Example
```bash
rtxmlrpc --as-import 'print="Hello world!"'
# This is equivalent to:
# $ echo 'print="Hello world!"' > /tmp/rtorrent-cmd
# $ rtxmlrpc import '' /tmp/rtorrent-cmd
# $ rm /tmp/rtorrent-cmd
```
