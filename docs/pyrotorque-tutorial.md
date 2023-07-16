# Pyrotorque Tutorial

Currently the existing pyrotorque documentation ranges from
[vague](usage-pyrotorque.md) to [very
detailed](pyrotorque-jobs.md). This will hopefully provide a more
pleasant introduction to the tool. For this tutorial, we're going to
focus on a few basic use cases:

* Load torrent files from `/var/rtorrent/watch/` without starting them
* Use QueueManager to start torrents in a controlled manner
* Move the data of completed torrents to a `/var/rtorrent/done`

All the configuration provided below should be placed under the
`[TORQUE]` section in `~/.config/pyrosimple/config.toml`. The full
configuration is provided at the end for reference.

## Load torrents

To start with, we'll use the `TreeWatch` class to load torrents. This
is very similar to the native `directory.watch.added` command, but has
several advantages, such as being able to pick up missing torrents.

The following configuration allows us to load all torrents under
`/var/rtorrent/watch/` and any of its subdirectories. The torrents are
loaded without being started, and every 15 minutes (as per `schedule`)
the directory is checked for any torrents that haven't been loaded (in
case they were added while pyrotorque or rTorrent wasn't running). It
also executes two user-defined commands via `cmd_custom_fields` to set
the `loaded_by` and `tracker_alias` fields. Finally,
`cmd_download_directory` sets the target directory to
`/var/rtorrent/downloading/`.

```toml
[TORQUE.load]
handler = "pyrocore.job.watch:TreeWatch"
schedule = "minute=*/15"
check_unhandled = true
path = "/var/rtorrent/watch/"
started = false
cmd_set_custom_fields = """
    d.custom.set=loaded_by,pyrotorque
    d.custom.set=tracker_alias,{{tracker_alias}}
"""
cmd_download_directory = "d.directory.set=/var/rtorrent/downloading/"
```

## Start torrents

Next we'll have pyrotorque start the loaded torrents in an orderly
fashion. This configuration tells pyrotorque to start torrents one at
at time every 5 minutes, up to a maximum of 20. However, the maximum
of 20 is deciding by only considering torrents that are actively
downloading data, so that the queue doesn't get stuck on dead
torrents. The `matcher` value is set to only start torrents which have
the `loaded_by` custom field set to `pyrotorque` (among other
filters), so that it doesn't interfere with other programs
(e.g. Radarr). It will also use `sort_fields` so that higher priority
torrents are started first.

```toml
[TORQUE.start]
handler         = "pyrocore.job.queue:QueueManager"
schedule        = "minute=*/5"
matcher         = "custom_loaded_by=pyrotorque is_ignored=no prio>0"
sort_fields     = "-prio,loaded,name"
start_at_once   = 1
downloading     = "is_active=yes is_complete=no down>0"
downloading_max = 20
```

## Move torrents

Every 10 minutes, this job will check for finished torrents and move
them. Ignored torrents and any actively transferring data are filtered
out.

```toml
[TORQUE.move_complete]
handler       = "pyrosimple.job.move_path:PathMover"
schedule      = "minute=*/10"
matcher       = "is_ignored=no is_complete=yes path=/var/rtorrent/downloading/* xfer=0"
target        = "/var/rtorrent/done"
```

## Full `config.toml`

```toml
[TORQUE]
[TORQUE.load]
handler = "pyrocore.job.watch:TreeWatch"
schedule = "minute=*/15"
check_unhandled = true
path = "/var/rtorrent/watch/"
started = false
cmd_set_custom_fields = """
    d.custom.set=loaded_by,pyrotorque
    d.custom.set=tracker_alias,{{tracker_alias}}
"""
cmd_download_directory = "d.directory.set=/var/rtorrent/downloading/"
[TORQUE.start]
handler         = "pyrocore.job.queue:QueueManager"
schedule        = "minute=*/5"
matcher         = "custom_loaded_by=pyrotorque is_ignored=no prio>0"
sort_fields     = "-prio,loaded,name"
start_at_once   = 1
downloading     = "is_active=yes is_complete=no down>0"
downloading_max = 20
[TORQUE.move_complete]
handler       = "pyrosimple.job.move_path:PathMover"
schedule      = "minute=*/10"
matcher       = "is_ignored=no is_complete=yes path=/var/rtorrent/downloading/* xfer=0"
target        = "/var/rtorrent/done"
```
