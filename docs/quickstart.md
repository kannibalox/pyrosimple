---
title: Quick Start
---

# Quick Start

The main goal of this document is to get you comfortable with using
pyrosimple to interact with rTorrent and torrent files. None of the
commands here will make any changes to your system and are intended to
be a gentle introduction to the many capabilities available.

## Setup

Install pyrosimple:

```bash
pip install pyrosimple
# pip install 'pyrosimple[torque]' # Optional dependencies for using pyrotorque
```

With pyrosimple installed and rTorrent running, let's see if the
configuration can be auto-detected:

```bash
pyroadmin config --check && echo "All good!"
```

If the command doesn't show any errors, then pyrosimple has
automatically figured out how to talk with rTorrent. Neat!

If not, see [Configuration](configuration.md) for instructions on how
to set up your config file, and come back once the command succeeds.

## Interacting with rTorrent

Let's start with something simple: `rtxmlrpc` is a command for
interacting with rTorrent's low-level API. Let's run some more
commands to get an idea of what it can do. None of these commands will
change anything, they'll just return information.

``` bash
# Get rTorrent's version
rtxmlrpc system.client_version
# Get the current download rate (in bytes/sec)
rtxmlrpc throttle.global_down.rate
# Get the name of all torrents in the 'main' view
rtxmlrpc d.multicall2 '' main d.name=
```

That's all very nice, but it'd be even nicer if there was a command to
make dealing with all the torrents easier than running all these RPC
commands. That's where `rtcontrol` comes into play. It allows for
scripting and outputting against torrents without needing to learn
rTorrent's RPC API directly. Try out the following commands:

``` bash
# Get all torrents in the 'main' view
rtcontrol //
# Get the hash of torrents in the 'main' view
rtcontrol // -o hash
# Get the size and name of completed torrents
rtcontrol is_complete=yes -o size.sz,name
# Get the upload, download and name of any not-ingnored active torrents
rtcontrol is_ignored=no xfer=+0 -o up.sz,down.sz,name
```

!!! note
    The string `//` in the first two commands is an empty regex. If
    you don't know what that means, don't worry, it's just an easy way
    to get all torrents.


`rtcontrol` lets us filter on different fields, and optionally pick
which fields will be output. The many different fields that are
available can be shown with `rtcontrol --help-fields`.  In addition to
simply displaying torrents, we can also run commands that will make
things change.

For the sake of this tutorial, all of the commands below have
`--dry-run` at the end to make sure nothing is changed. If you'd like
to try running the commands for real, simply remove that flag.

```bash
# Start all torrents
rtcontrol // --start --dry-run
# Set a custom field on all active torrents
rtcontrol xfer=+0 --custom test=hello --dry-run
# Hash check all un-ignored completed torrents
rtcontrol is_ignored=no is_complete=yes --hash-check --dry-run
```

## Working with torrents

In addition to rTorrent, pyrosimple can also work with .torrent files
directly. The commands `mktor`, `lstor` and `chtor` can make, list,
and modify files, respectively.

Let's try creating an example torrent from an example file
with the (fake) tracker `http://example.com`.

```bash
date > example.txt
mktor -o example.torrent example.txt http://example.com
```

Now we can check our newly created torrent:

```bash
lstor example.torrent
```

It looks pretty good, but maybe there should be a comment added to it.

```bash
chtor --comment 'Hello world!' example.torrent
# View the changed file
lstor example.torrent
```

## Next steps

-   All of the commands listed above have many more capabilities than what
    is shown here. Refer to their respective User Guide pages for a
    full explanation of what each tool can do.
    -   `rtcontrol` in particular has many uses, as seen in
        [rtcontrol's usage page](usage-rtcontrol.md)
-   See [Advanced Usage](advanced.md) for more advanced examples
    of the things that can be done with pyrosimple.
