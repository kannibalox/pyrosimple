---
title: mktor/lstor/chtor Usage
---
# mktor/lstor/chtor

The following tools are grouped together due to their similar
functionality. They can create, view, and modify .torrent files
respectively.

## lstor

lstor is used for displaying information about torrents. Without any
flags, it shows a human-friendly summary of the torrent:

```
$ lstor ubuntu-22.04-desktop-amd64.iso.torrent
NAME ubuntu-22.04-desktop-amd64.iso.torrent
SIZE 3.4 GiB (13942 * 256.0 KiB + 142.0 KiB)
META 272.7 KiB (pieces 272.3 KiB 99.9%)
HASH 2C6B6858D61DA9543D4231A71DB4B1C9264B0685
URL  https://torrent.ubuntu.com/announce
PRV  NO (DHT/PEX enabled)
TIME 2022-04-21 10:22:56
BY   mktorrent 1.1
REM  Ubuntu CD releases.ubuntu.com

FILE LISTING
ubuntu-22.04-desktop-amd64.iso                                         3.4 GiB
```

However, you can also display the same information in JSON format with
the `--raw` flag:
```
lstor ubuntu-22.04-desktop-amd64.iso.torrent --raw
```
```json
{
  "announce": "https://torrent.ubuntu.com/announce",
  "announce-list": [
    [
      "https://torrent.ubuntu.com/announce"
    ],
    [
      "https://ipv6.torrent.ubuntu.com/announce"
    ]
  ],
  "comment": "Ubuntu CD releases.ubuntu.com",
  "created by": "mktorrent 1.1",
  "creation date": 1650550976,
  "info": {
    "length": 3654957056,
    "name": "ubuntu-22.04-desktop-amd64.iso",
    "piece length": 262144,
    "pieces": "<13943 piece hashes>"
  }
}
```

If you only need to extract a few fields, the `-o`/`--output` flag
lets you specify which fields to show:

```
$ lstor -o info.name,__size__ ubuntu-22.04-desktop-amd64.iso.torrent
ubuntu-22.04-desktop-amd64.iso	3654957056
```

!!! note
    `__size__` is a magic variable that tells `lstor` to sum the
    sizes of all files in the torrent. See `lstor --help` for all the
    supported magic variables.


By default lstor will throw an error if the file isn't a valid
.torrent file. However, if you wish to ignore those errors (to view a
rTorrent session file, for instance), the `--raw` flag can be combined
with `-V`/`--skip-validation`.

`lstor` can also hash check the torrent against real data by using the `-H <path>` flag.

## mktor

At its simplest, creating a torrent file requires only a path and an announce URL:

```bash
date > date.txt
mktor date.txt http://tracker.publicbt.com:80/announce
```

If you have [aliases](configuration.md#aliases) configured, you can
use the alias in place of the URL.

```toml title="config.toml"
[ALIASES]
PUB_BT = ["http://tracker.publicbt.com:80/announce"]
```
```bash
mktor date.txt PUB_BT
```

### Cross-seeding

To avoid duplicating the same hash across private trackers, mktor has
two mechanisms to add distinct data to the `info` dictionary:

* `source` gets set to the tracker alias (if available), or the 2nd
  level domain if not available
* `x_cross_seed` gets set to an MD5 hash of the URL

If you don't want one or both of these fields present, you can use the
`-s`/`--set` flag to have them removed:

```
mktor --set info.source --set info.x_cross_seed date.txt http://tracker.publicbt.com:80/announce
```

## chtor

If you have an existing .torrent file you'd like to change, whether
created by `mktor` or an entirely different program, `chtor` is your
friend.

!!! warning

    Changing any fields in the `info` section of the data will change
    the torrent hash, which may have unintended consequences.

The simplest way to change data is the `-s`/`--set` flag, which can
add, change, or remove fields:

```bash
date > date.txt
mktor date.txt http://tracker.publicbt.com:80/announce
lstor --raw date.torrent
chtor --set "last changed=$(date)" date.torrent # Add \
  --set "created by=PyroSimple v2" # Change \
  --set "creation date=" # Remove
lstor --raw date.torrent
```

There's also a similar flag to set fields with a regex:

```bash
chtor --regex "created by/PyroSimple/PyroChanged/" date.torrent
```

There are many other flags available to perform common operations, such as
removing non-standard fields (`--clean`) or adding fast resume data
(`--datapath <DATA>`).
