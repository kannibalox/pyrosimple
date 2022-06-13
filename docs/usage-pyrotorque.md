---
title: Usage
---

# pyrotorque

The `pyrotorque` command is a daemon that handles background jobs. At
first, it was just a flexible torrent queue manager for starting items
one at a time (thus the name `pyro-tor-que`), but it can now manage any
job that does some background processing for rTorrent, including custom
ones that you can add yourself.

There are two primary jobs that can be run from pyrotorque:

* A tree watcher that reacts via `inotify` to load new files into rtorrent as needed.
  It functions very similarly to `directory.watch.added`, but allows for more complex 
  loading rules, as well as recursive watching.
* A queue manager that handles starting torrents in a controlled manner. This ensures
  that a system is not overloaded by starting too many torrents at once. The job is compatible
  with torrents from both the tree watcher and files loaded by `directory.watch.added` or a `load` schedule.

## Configuration

The configuration lives in the same `config.toml` with everything else, in the `[TORQUE]` section. Under the section, there are settings for pyrotorque itself, and then sub-sections for the individual jobs.

Example:
```toml
[TORQUE]
[TORQUE.stats]
handler = "pyrocore.torrent.jobs:EngineStats"
schedule = "minute=*"
active = true
dry_run = true
[TORQUE.watch]
handler = "pyrocore.torrent.watch:TreeWatch"
schedule = "minute=*"
active = true
dry_run = true
path = "/tmp/watch"
cmd.test = "d.custom=test"
[TORQUE.queue]
handler = "pyrocore.torrent.watch:QueueManager"
schedule = "hour=*"
active = true
dry_run = true
```

As seen in the `stats` job, there are four main settings for a job:

- `handler` defines what class will run. You shouldn't need to understand what this means unless you're writing custom jobs, see the handler reference below instead.
- `schedule` tells pyrotorque when to trigger jobs. If you're familiar with cron syntax, this is very similiar, e.g. `minute=*` means run once a minute. The underlying library, APScheduler, extends the syntax with features like per-second resolution, check out the [documentation](https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html#introduction) for details.
- `active` provides an easy way to enable or disable jobs.
- `dry_run` tells the job to not make any actual changes if it's `true`.

Any other settings are job-specific. For more detail documentation for each job, see the [pyrotorque reference](/pyrotorque-jobs/)

## Usage

Once you have a configuration file, the easiest way to test your configuration is to try running the process in the foreground:

```bash
# Also enforce `dry_run = true` and output messages while we're testing things
pyrotorque --fg --dry-run -v
```

Alternatively, you can also test the individual jobs one run at a time:
```bash
pyrotorque --run-once stats --dry-run --debug
```

Once you're satisfied, you can launch the process into the background by simply running `pyrotorque`. You can check the status, restart, or stop the daemon with `--status`, `--restart` and `--stop` respectively. Alternatively, see your distro's documentation for writing service files. Here is a bare-bones example for a systemd-based distro:

```ini
[Unit]
Description=Pyrotorque rtorrent daemon
After=network-online.target rtorrent.service
Wants=rtorrent.service

[Service]
Type=simple
ExecStart=pyrotorque --fg

[Install]
WantedBy=multi-user.target
```
