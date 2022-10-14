---
title: Pyrotorque Jobs
---

# Pyrotorque Jobs

## Command

This job runs a single untemplated command. While this can also be
done with straight cron, having it in pyrotorque allows keeping all
rTorrent changes in one place. It also offers several improvements,
such as per-second resolution.

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
* `view`: The rtorrent view to query
* `matcher`: The query to use when listing torrents

## Queue Manager

### Configuration

The following is a minimal `config.toml` configuration example, only
changing a few values from the defaults to demonstrate key features:

```toml
[TORQUE.queue]
handler = "pyrocore.torrent.queue:QueueManager"
schedule = "minute=*"
sort_fields = "-prio,loaded,name"
#startable = "is_open=no tagged=torqued is_ignored=no done=0 message=''"
downloading_min = 1
downloading_max = 100
```

Having a minimal configuration with just your changes is recommended,
so you get new defaults in later releases automatically.

### Queue Settings Explained

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

This job is for loading torrents into rtorrent. While the native tools
work well enough for simply loading torrents, this jobs allows for
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
* `remove_already_added`: If true, pytorque will remove files if the
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
$ pyrotorque --dry-run --debug --run-once watch
…
DEBUG    Tree watcher created with config Bunch(active=False, …
    cmd.target='{{# set target path\n}}d.custom.set=targetdir,/var/torrent/done/{{label}}/{{relpath}}',
    dry_run=True, handler='pyrosimple.job.watch:TreeWatch', job_name='treewatch',
    load_mode='start', path='/var/torrent', queued='True', quiet='False', schedule='hour=*')
DEBUG    custom commands = {'target': <Template 2d01990 name=None>, 'nfo': f.multicall=*.nfo,f.set_priority=2, …}
DEBUG   Templating values are:
    commands=[…, 'd.custom.set=targetdir,/var/torrent/done//pyrocore', …]
    filetype='.dat'
    …
    info_hash='8D59E3FD8E78CC9896BDE4D65B0DC9BDBA0ADC70'
    info_name='example.dat'
    label=''
    pathname='/var/torrent/pyroscope/example.dat.torrent'
    relpath='pyrocore'
    tracker_alias='tracker.example.com'
    traits=Bunch(kind=None)
    watch_path=set(['/var/torrent'])
```

Things to take note of:

1.  the `target` custom command is expanded to set the `targetdir`
    rTorrent attribute to the completion path (which can then be used
    in a typical `event.download.finished` handler), using the
    `relpath` variable which is obtained from the full `.torrent`
    path, relative to the watch dir root.

2.  all kinds of other information is made available, like the
    torrent's info hash and the tracker alias; thus you can write
    conditional templates based on tracker, or use the tracker name in
    a completion path.

3.  for certain types of downloads, `traits` provides parsed
    information to build specific target paths, e.g. for the
    `Pioneer.One.S01E06.720p.x264-VODO` TV episode, you'll get this:

    ``` ini
    label='tv/mkv'
    traits=Bunch(aspect=None, codec='x264', episode='06', extension=None, format='720p',
        group='VODO', kind='tv', pattern='Normal TV Episodes', release=None,
        release_tags=None, season='01', show='Pioneer.One', sound=None, title=None)
    ```

### Tree Watch Examples

#### Completion Moving

Since the templating namespace automatically includes the path of a
loaded `.torrent` file relative to the watch root (in `relpath`, see
above example namespace output and the config example further down),
you can set the \"move on completion\" target using that value.

``` ini
job.treewatch.cmd.target    = {{# set target path
    }}d.custom.set=targetdir,/var/torrent/done/{{label}}/{{relpath}}
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
