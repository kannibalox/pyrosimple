---
title: Pyrotorque Jobs
---

# Pyrotorque Jobs

## Command

This job runs a single untemplated command. While this can also be
done with straight cron, having it in pyrotorque allows keeping all
rTorrent changes in one place. It also offers several improvements,
such as per-second resolution.

### Configuration

```toml
[TORQUE.send_mail]
handler       = "pyrosimple.job.action:Command"
args          = "echo 'pyrotorque is still running!' | mail -s 'pyrotorque check'"
shell         = true
schedule      = "hour=*"
```

There are optional parameters `shell`, `cwd`, `timeout`, `check`, and
`env`, all of which correspond to the parameters of
[`subprocess.run()`](https://docs.python.org/3/library/subprocess.html#subprocess.run)

## Item Command

This job is very similar to Command, but instead runs a templated
command against all matching items.

### Configuration

```toml
[TORQUE.log_messaages]
handler       = "pyrosimple.job.action:ItemCommand"
args          = "echo '{{item.hash}} has message {{item.message}}' >> /var/log/rtorrent/messages.log"
shell         = true
schedule      = "hour=*"
matcher       = "message=/.+/"
view          = "default"
```

There are optional parameters `shell`, `cwd`, `timeout`, `check`, and
`env`, all of which correspond to the parameters of
[`subprocess.run()`](https://docs.python.org/3/library/subprocess.html#subprocess.run)

## Action Job

This is a simple job, intended to allow access to (almost)
the same actions as `rtcontrol`.

### Configuration

Example of stopping completed torrents after they reach a >5 ratio:

```toml
[TORQUE.stop_well_seeded]
handler       = "pyrosimple.job.action:Action"
schedule      = "hour=*"
matcher       = "is_ignored=no ratio>5.0"
view          = "complete"
action        = "stop"
```

Arguments:

* `action`: The action to perform. See `rtcontrol --help` for a list
  of actions.
* `view`: The rTorrent view to query
* `matcher`: The query to use when listing torrents

## Queue Manager

### Configuration

The following is a minimal `config.toml` configuration example, only
changing a few values from the defaults to demonstrate key features:

```toml
[TORQUE.queue]
handler = "pyrosimple.job.queue:QueueManager"
schedule = "minute=*"
sort_fields = "-prio,loaded,name"
matcher = "is_open=no tagged=torqued is_ignored=no done=0 message=''"
downloading_min = 1
downloading_max = 100
```

Having a minimal configuration with just your changes is recommended,
so you get new defaults in later releases automatically.

Arguments:

* `matcher`/`startable`  
  The query to use to determine which torrents are valid candidates to
  be started.
* `start_at_once`  
  The maximum number of items to start during a single run. May be
  overridden by the `downloading_min` settings. Defaults to `1`.
* `downloading`  
  The query used to determine the number of actively downloading
  torrents. Defaults to `is_active=1 is_complete=0`
* `downloading_min`  
  If the number of actively downloading torrents is less than this
  number, the job will ignore `start_at_once` to get to this
  number. Defaults to `0` (meaning `start_at_once` will always be
  honored).
* `downloading_max`  
  If the number of actively downloading torrents is greater than this
  number, pyrotorque will not start any items. Defaults to `20`.
* `intermission`  
  If any items are started, pyrotorque will wait this many seconds
  before attempting to start another. This is helpful to avoid
  potentially starting too many items too quickly. Defaults to `120`.
* `max_downloading_traffic`  
  If set, this setting will skip starting torrents when the torrents
  in `downloading` exceed this value.
* `log_to_client`  
  Can be set to `False` to avoid logging messages in rTorrent whenever
  a torrent is started. Defaults to `True`.

### Explanation

In the above example for the `queue` job, `downloading_max` counts
started-but-incomplete items including those that ignore
commands. Only if there are fewer of these items in the client than
that number, a new item will be started. This is the queue's length
and thus the most important parameter.

The queue *never* stops any items, i.e. `downloading_max` is not
enforced and you can manually start more items than that if you want
to.  That is also the reason items that should be under queue control
must be loaded in 'normal' mode, i.e. stopped.

Other queue parameters are the minimum number of items in
'downloading' state named `downloading_min`, which trumps
`start_at_once`, the maximum number of items to start in one run of
the job. Both default to `1`. Since the default schedule is
`second=*/15`, that means at most one item would be started every 15
seconds.

But that default is changed using the following two lines:

```toml
schedule          = "second=*/5"
intermission      = 60
```

This makes the queue manager check more often whether there is
something startable, but prevents it from starting the next batch of
items when the last start was less than `intermission` seconds ago.

The `startable` condition (repeated below for reference) prevents
ignored items, ones having a non-empty message, and those with the
lowest priority from being started. Note that tree watch sets the
priority of items loaded in 'normal' mode to zero -- that `prio>0`
condition then excludes them from being started automatically some
time later, until you press `+` to increase that priority. You can
also delay not-yet-started items using the `-` key until the item has
a priority of zero (a/k/a `off`).

```toml
startable = '''
        is_ignored=0 message= prio>0
        [ prio>2 OR [ NOT [ traits=audio kind_25=jpg,png,tif,bmp ] ] ]
'''
```

This sample condition also adds the extra hurdle that audio downloads
that don't stay below a 25% threshold regarding contained images are
**not** started automatically. *Unless* you raise the priority to 3
(`high`) using the `+` key, then they're fair game for the queue. Go
do all that with a plain rTorrent watch dir, in one line of
configuration.

The parameter `sort_fields` is used to determinate in what order
startable items are handled. By default, higher priority items are
started first, and age is used within each priority class.

Above, it was mentioned `downloading_max` counts
started-but-incomplete items. The exact definition of that
classification can be changed using the `downloading` condition. A
given condition is *always* extended with `is_active=1 is_complete=0`,
i.e. the started-but-incomplete requirement.

```toml
downloading = "[ prio>1 [ down>3 OR started<2 ] ]"
```

In plain English, this example says we only count items that have a
normal or high priority, and transfer data or were started in the last
2 minutes. The priority check means you can 'hide' started items from
the queue by setting them to `low`, e.g. because they're awfully slow
and prevent your full bandwidth from being used.

The second part automatically ignores stalled items unless just
started.  This prevents disk trashing when a big item is still
creating its files and thus has no data transfer -- it looks stalled,
but we do not want yet another item to be started and increasing disk
I/O even more, so the manager sees those idle but young items as
occupying a slot in the queue.

## Tree Watch

This job is for loading torrents into rTorrent. While the native tools
work well enough for simply loading torrents, this job allows for
additional features like conditional logic and invalid file handling.

Note that this job uses inotify, which is much lighter-weight but has
the potential to miss files. See the `check_unhandled` argument for a
way to counter this issue.

### Configuration

```toml
[TORQUE.watch]
handler = "pyrocore.job.watch:TreeWatch"
schedule = "second=*/5"
path = "/var/torrents/watch"
started = false
check_unhandled = true
remove_already_added = true
cmd_label = """
{% if 'TV' in flags %}d.custom1.set=TV{% endif %}
"""
```

Arguments:

* `path`: The path to watch for new files. Multiple paths can be
  separate with `:`. Note that the watch is recursive.
* `started`: Controls whether new items are automatically started
  after adding
* `check_unhandled`: If true, the job will try to find and update any
  file it may have missed on each `schedule`. This will also catch any
  files that were added while pyrotorque wasn't running
* `remove_already_added`: If true, pyrotorque will remove files if the
  hash already exists in the client. This is mainly useful to prevent
  errors and files from building up if files are accidentally added to
  the directory twice.
* `cmd_*`: Any argument starting with this prefix is treated as a
  custom command that will be run when the torrent is loaded. As seen
  in the example, this can be a fully-templated string, with some
  fields being auto-created by the job itself.

### Explanation

As mentioned in `QueueManager`, commands configured to be executed
during item loading can be templates. This can be used to support all
sorts of tricks, the most common ones are explained here, including
fully dynamic completion moving. If the following explanation of the
inner workings is too technical and nerdy for you, skip to the [tree
watch examples](pyrotorque-jobs.md#tree-watch-examples) section below,
and just adapt one of the prepared use cases to your setup.

So how does this work? When a `.torrent` file is notified for loading
via `inotify`, it's parsed and contained data is put into variables
that can be used in the command templates. In order to get an idea
what variables are available, you can combine the dry-run and debug
modes.

Consider this example:

``` shell
$ cd /var/torrent/watch
$ date >example.dat
$ mktor -q example.dat http://tracker.example.com/
$ python -m pyrosimple.job.watch
2022-11-25 11:21:47,588  INFO job:: Building template variables for '/var/torrent/watch/example.torrent'
2022-11-25 11:21:47,597  INFO job:: Available variables: {'commands': [],
 'filetype': '.dat',
 'flags': {'example.torrent', 'example', 'var', 'torrent', 'watch'},
 'info_hash': '96336C9C3A1D8EC99C02FF79115476DDD4474A7A',
 'info_name': 'example.dat',
 'pathname': '/var/torrent/watch/example.torrent',
 'rel_path': 'example.torrent',
 'tracker_alias': 'example.com',
 'watch_path': {'/var/torrent/watch/'}}
```

Things to take note of:

1.  All kinds of information is made available, like the
    torrent's info hash and the tracker alias; thus you can write
    conditional templates based on tracker, or use the tracker name in
    a completion path.

2.  For certain types of downloads, `traits` provides parsed
    information to build specific target paths, e.g. for the
    `Pioneer.One.S01E06.720p.x264-VODO` TV episode, you'll get this:

    ``` ini
    label='tv/mkv'
    traits=Bunch(aspect=None, codec='x264', episode='06', extension=None, format='720p',
        group='VODO', kind='tv', pattern='Normal TV Episodes', release=None,
        release_tags=None, season='01', show='Pioneer.One', sound=None, title=None)
    ```

### Examples

#### Completion Moving

Since the templating namespace automatically includes the path of a
loaded `.torrent` file relative to the watch root (in `relpath`, see
above example namespace output and the config example further down),
you can set the \"move on completion\" target using that value.

``` ini
cmd_target    = {# set target path
    #}d.custom.set=targetdir,/var/torrent/done/{{label}}/{{relpath}}
```

Note that this still needs a typical completion event handler that takes
the custom variable that is set, and moves the data based on its value.

#### Tree Watch with Sorting

This example adds a *second* job for a `sorted` tree that directly saves
the data into a path based on the loaded metafile's location.

```ini
# Tree watch with location
job.watch-sorted.handler        = pyrocore.torrent.watch:TreeWatch
job.watch-sorted.schedule       = hour=*
job.watch-sorted.active         = True

job.watch-sorted.load_mode      = normal
job.watch-sorted.queued         = True
job.watch-sorted.path           = /var/torrent/sorted/watch
job.watch-sorted.cmd.setdir     = {{# set download path
    }}{{if '/music/' in pathname}}{{# add metafile basename to path
        }}d.directory_base.set="/var/torrent/sorted/{{relpath}}/{{pathname|h.pathname}}"{{#
    }}{{elif traits.kind == 'tv'}}{{# store TV content into separate show folders
        }}d.directory.set="/var/torrent/sorted/{{relpath}}/{{traits.get('show', '_UNKNOWN').replace('.',' ').title()}}"{{#
    }}{{else}}{{# just use the relative metafile location
        }}d.directory.set="/var/torrent/sorted/{{relpath}}"{{#
    }}{{endif}}
```

Change the values in the second block to suit your needs. As given, an
item loaded from `…/sorted/watch/movies/*.torrent` would end up in the
`…/sorted/movies` directory (with the filename coming from inside the
metafile as usual), and it won't start by itself.

Also, paths containing `music` use the metafile's basename as the data
directory, and metafiles recognized as TV content get separated into
show directories.
