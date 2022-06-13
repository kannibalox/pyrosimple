---
title: Advanced Features
---

!!! note
    Using these features requires some knowledge in the area Linux, Bash,
    and Python beyond a novice level, but they enable you to customize your
    setup even further and handle very specific use-cases.

# Advanced 'rtcontrol'

## Executing OS commands

The `--call` and `--spawn` options can be used to call an OS level
command and feed it with data from the selected items. The argument to
both options is a template, i.e. you can have things like
`{{item.hash}}` in them.

When using `--call`, the command is passed to the shell for parsing --
with obvious implications regarding the quoting of arguments, thus
`--call` only makes sense if you need I/O redirection or similar shell
features.

In contrast, the `--spawn` option splits its argument list according to
shell rules *before* expanding the template placeholders, and then calls
the resulting sequence of command name and arguments directly. Consider
`--spawn 'echo "name: {{i.name}}"'` vs.
`--spawn 'echo name: {{i.name}}'` -- the first form passes one
argument to `/bin/echo`, the second form two arguments. Note that in
both cases, spaces or shell meta characters contained in the item name
are of no relevance, since the argument list is split according to the
template, *not* its expanded value.

To list all the fields available in the first five items, try this
command:

``` bash
rtcontrol // -/5 --spawn "echo -e '\\n'{{i}}" | sed -re 's/, /,\n    /g'
```

Unlike `--call`, where you can use shell syntax to call several
commands, `--spawn` can be passed several times for executing a sequence
of commands. If any called command fails, the `rtcontrol` call is
aborted with an error.

### Copy Session Metafiles by Category

Here\'s a practical example for using `--spawn`, it copies all your
loaded metafiles from the session directory into a folder structure
categorized by the *ruTorrent* label. Unlabelled items go to the
`_NOLABEL` folder.

``` bash
target="/tmp/metafiles"
rm -rf "$target"
rtcontrol // \
    --spawn "mkdir -p \"$target/"'{{i.fetch(1) or \"_NOLABEL\"}}"' \
    --spawn 'cp {{i.sessionfile}} "'"$target"'/{{item.fetch(1) or \"_NOLABEL\"}}/{{item.name}}-{{item.hash[:7]}}.torrent"'
```

The copied metafiles themselves are renamed to the contained name of the
item\'s data, plus a small part of the infohash to make these names
unique.

Replace the `i.fetch(1)` by `i.‹fieldname›` to categorize by other
values, e.g. `i.alias` for 'by tracker'.

## Executing XMLRPC commands {#rtcontrol-exec}

If you want to apply some custom XMLRPC commands against a set of
download items, the `--exec` option of `rtcontrol` allows you to do
that. For global commands not referring to specific items, see the next
section about the `rtxmlrpc` tool. Read through the following examples
to understand how `--exec` works, features are explained as they are
used there. Also make sure you understand basic things like
`output-templates`{.interpreted-text role="ref"} beforehand, it\'s
assumed here that you do.

### Repairing Stuck Items

Let\'s start with an easy example of using `--exec`, where no templating
is needed:

``` bash
rtcontrol --exec 'stop= ; close= ; f.multicall=,f.set_create_queued=0,f.set_resize_queued=0 ; check_hash=' \
          --from stopped // -/1
```

This command simulates pressing `^K^E^R` in the curses UI (which cleans
the state of stuck / damaged items), and as written above only affects
the first stopped item.

Use different filter arguments after `--exec` to select other items.
Afterwards, use `--start` to start these items again.

### Manually Triggering Events

Since rTorrent events are merely multi-call commands, you can trigger
them manually by calling them on selected items. This calls
`event.download.finished` (again) on complete items loaded
in the last 10 minutes:

``` bash
rtcontrol --exec ":event.download.finished=" 'loaded<10m' is_complete=y
```

The `:` prefix prevents `rtcontrol` from assuming this is a `d.` item
command.

Make sure that the registered handlers do not have adverse effects when
called repeatedly, i.e. know what you\'re doing. The handlers for an
event can be listed like so:

``` bash
rtxmlrpc --repr method.get '' event.download.finished
```

### Relocating Download Data

The most simple variant of changing the download path is setting a new
fixed location for all selected items, as follows:

``` bash
rtcontrol --exec 'directory_base.set="/mnt/data/new/path"' directory=/mnt/data/old/path
```

This replaces the location of items stored at `/mnt/data/old/path` with
a new path. But to be really useful, we\'d want to shift *any* path
under a given base directory to a new location -- the next command does
this by using templating and calculating the new path based on the old
one:

``` bash
rtcontrol \
    --exec 'directory_base.set="{{item.directory|subst("^/mnt/data/","/var/data/")}}" ; >directory=' \
    directory=/mnt/data/\*
```

This selects any item stored under `/mnt/data` and relocates it to the
new base directory `/var/data`. Fields of an item can be used via a
`item.‹field-name›` reference. Adding `>directory=` prints the new
location to the console -- a semicolon with spaces on both sides
delimits several commands, and the `>` prints the result of a XMLRPC
command. Also note that the `d.` prefix to download item commands is
implied.

The `move-data`{.interpreted-text role="ref"} section has more on how to
also move the data on disk, in addition to changing the location in
[rTorrent]{.title-ref}\'s session as shown here.

### Making Shared Data Paths Unique

Another example regarding data paths is this:

``` bash
rtcontrol --from stopped // --exec 'directory.set={{item.directory}}-{{item.hash}}'
```

That command ensures that items that would download into the same path
get a unique name by appending the info hash, and assumes those items
weren\'t started yet (i.e. added via `load.normal`).

### Changing Announce URLs in Bulk

The next example replaces an active announce URL with a new one, which
is necessary after a domain or passkey change. Compared to other methods
like using `sed` on the files in your session directory, this does not
require a client restart, and is also safer (the `sed` approach can
easily make your session files unusable). This disables all old announce
URLs in group 0 using a `t.multicall`, and then adds a new one:

``` bash
rtcontrol \
    --exec 't.multicall=0,t.disable= ; tracker.insert=0,"http://new.example.com/announce" ; save_full_session=' \
    "tracker=http://old.example.com/announce"
```

The `tracker.insert` also shows that arguments to commands can be
quoted.

## Using Templates as Filter Values

As mentioned in `filter-conditions`, you
can compare a string field to a template. This can be a brain twister,
so just look at the following example, which replaces any download path
in an item by the real storage path, but only if they differ.

``` bash
# List any differences
rtcontrol path='*' is_multi_file=y 'directory!={{d.realpath}}' \
    -qo directory,realpath
rtcontrol path='*' is_multi_file=n 'directory!={{d.realpath | pathdir}}' \
    -qo directory,realpath.pathdir

# Fix any differences (i.e. resolve all symlinks for good)
rtcontrol path='*' is_multi_file=y 'directory!={{d.realpath}}' \
    --exec 'directory_base.set={{item.realpath}}'
rtcontrol path='*' is_multi_file=n 'directory!={{d.realpath | pathdir}}' \
    --exec 'directory.set={{item.realpath | pathdir}}'
```

As so often, 'multi' and 'single' items need a slighty different
treatment.

Note that `[` characters are escaped to `[[]` after the template
expansion, so that things like `[2017]` in a filename do not lead to
unexpected results. `*` and `?` though are kept intact and are used for
glob matching as normal, because they match their own literal form if
they appear in the field value (on the right-hand side).

# Using 'rtxmlrpc'

## Querying system information

The `rtuptime` script shows you essential information about your
*rTorrent* instance:

::: {.literalinclude language="shell"}
examples/rtuptime
:::

When called, it prints something like this:

``` console
$ rtuptime
rTorrent 0.9.6/0.13.6, up 189:00:28 [315 loaded; U: 177.292 GiB; S: 891.781 GiB],
D: 27.3 GB @ 0.0 KB/s of 520.0 KB/s, U: 36.8 MB @ 0.0 KB/s of 52.0 KB/s
```

And yes, doing the same in a `Python script <scripts>`{.interpreted-text
role="ref"} would be much more CPU efficient. ;)

If you connect via `network.scgi.open_port`, touch a file in `/tmp` in
your startup script and use that for uptime checking.

## Load Metafile with a Specific Data Path

The following shows how to load a metafile from any path in `$metafile`,
not only a watch directory, with the data downloaded to `$data_dir` by
adding a `d.directory_base.set` on-load command. You might need to
change that to `d.directory.set` depending on your exact use-case.

``` shell
rtxmlrpc -q load.normal '' "$metafile" \
    "d.directory_base.set=\"$data_dir\"" "d.priority.set=1"
```

Use `load.start` to start that item immediately. If the metafile has
fast-resume information and the data is already there, no extra hashing
is done.

And just to show you can add more on-load commands, the priority of the
new item is set to `low`. Other common on-load commands are those that
set custom values, e.g. the *ruTorrent* label.

## General maintenance tasks

Here are some commands that can help with managing your rTorrent
instance:

``` shell
# Flush ALL session data NOW, use this before you make a backup of your session directory
rtxmlrpc session.save
```

## Setting and checking throttles

To set the speed of the `slow` throttle, and then check your new limit
and print the current download rate, use:

``` console
$ rtxmlrpc throttle.down '' slow 120
0
$ rtxmlrpc throttle.down.max '' slow
122880
$ rtxmlrpc throttle.down.rate '' slow
0
```

Note that the speed is specified in KiB/s as a string when setting it
but returned in bytes/s as an integer on queries.

The following script makes this available in an easy usable form, e.g.
`throttle slow 42` -- it also shows the current rate and settings of all
defined throttles when called without arguments:

``` shell
#! /bin/bash
# Set speed of named throttle

#
# CONFIGURATION
#
throttle_name="seed" # default name
unit=1024 # KiB/s

#
# HERE BE DRAGONS!
#
down=false
if test "$1" = "-d"; then
    down=true
    shift
fi

if test -n "$(echo $1 | tr -d 0-9)"; then
    # Non-numeric $1 is a name
    throttle_name=$1
    shift
fi

if test -z "$1"; then
    echo >&2 "Usage: ${0/$HOME/~} [-d] [<throttle-name=$throttle_name>] <rate>"

    rtorrent_rc=~/.rtorrent.rc
    test -e "$rtorrent_rc" || rtorrent_rc="$(rtxmlrpc system.get_cwd)/rtorrent.rc"
    if test -e "$rtorrent_rc"; then
        throttles="$(egrep '^throttle[._](up|down)' $rtorrent_rc | tr ._=, ' ' | cut -f3 -d" " | sort | uniq)"
        echo
        echo "CURRENT THROTTLE SETTINGS"
        for throttle in $throttles; do
            echo -e "  $throttle\t" \
                "U: $(rtxmlrpc to_kb $(rtxmlrpc throttle.up.rate $throttle)) /" \
                "$(rtxmlrpc to_kb $(rtxmlrpc throttle.up.max $throttle | sed 's/^-1$/0/')) KiB/s\t" \
                "D: $(rtxmlrpc to_kb $(rtxmlrpc throttle.down.rate $throttle)) /" \
                "$(rtxmlrpc to_kb $(rtxmlrpc throttle.down.max $throttle | sed 's/^-1$/0/')) KiB/s"
        done
    fi
    exit 2
fi

rate=$(( $1 * $unit ))

# Set chosen bandwidth
if $down; then
    if test $(rtxmlrpc throttle.down.max $throttle_name) -ne $rate; then
        rtxmlrpc -q throttle.down $throttle_name $(( $rate / 1024 ))
        echo "Throttle '$throttle_name' download rate changed to" \
             "$(( $(rtxmlrpc throttle.down.max $throttle_name) / 1024 )) KiB/s"
    fi
else
    if test $(rtxmlrpc throttle.up.max $throttle_name) -ne $rate; then
        rtxmlrpc -q throttle.up $throttle_name $(( $rate / 1024 ))
        echo "Throttle '$throttle_name' upload rate changed to" \
             "$(( $(rtxmlrpc throttle.up.max $throttle_name) / 1024 )) KiB/s"
    fi
fi
```

## Global throttling when other computers are up

If you want to be loved by your house-mates, try this:

``` shell
#! /bin/bash
# Throttle bittorrent when certain hosts are up

#
# CONFIGURATION
#
hosts_to_check="${1:-mom dad}"
full_up=62
full_down=620
nice_up=42
nice_down=123
unit=1024 # KiB/s

#
# HERE BE DRAGONS!
#

# Check if any prioritized hosts are up
up=$(( $full_up * $unit ))
down=$(( $full_down * $unit ))
hosts=""

for host in $hosts_to_check; do
    if ping -c1 $host >/dev/null 2>&1; then
        up=$(( $nice_up * $unit ))
        down=$(( $nice_down * $unit ))
        hosts="$hosts $host"
    fi
done

reason="at full throttle"
test -z "$hosts" || reason="for$hosts"

# Set chosen bandwidth
if test $(rtxmlrpc throttle.global_up.max_rate) -ne $up; then
    echo "Setting upload rate to $(( $up / 1024 )) KiB/s $reason"
    rtxmlrpc -q throttle.global_up.max_rate.set_kb $(( $up / 1024 ))
fi
if test $(rtxmlrpc throttle.global_down.max_rate) -ne $down; then
    echo "Setting download rate to $(( $down / 1024 )) KiB/s $reason"
    rtxmlrpc -q throttle.global_down.max_rate.set_kb $(( $down / 1024 ))
fi
```

Add it to your crontab and run it every few minutes.

## Throttling rTorrent for a limited time

If you want to slow down *rTorrent* to use your available bandwidth on
foreground tasks like browsing, but usually forget to return the
throttle settings back to normal, then you can use the provided
[rt-backseat]() script. It will register a job via `at`, so that command
must be installed on the machine for it to work. The default throttle
speed and timeout can be set at the top of the script.

::: {.literalinclude language="bash"}
examples/rt-backseat
:::

::: {#rt-backseat}
> <https://github.com/pyroscope/pyrocore/blob/master/docs/examples/rt-backseat>
:::

# rTorrent Queue Manager {#QueueManager}

## Introduction

The `pyrotorque` command is a daemon that handles background jobs. At
first, it was just a flexible torrent queue manager for starting items
one at a time (thus the name `pyro-tor-que`), but it can now manage any
job that does some background processing for rTorrent, including custom
ones that you can add yourself.

It runs in the background parallel to rTorrent and has its own scheduler
to run automation jobs similar to rTorrent\'s `schedule` command --- one
of the jobs does start stopped items in a controlled fashion, that is
the queue manager part.

Besides the queue manager, the most important job type is `TreeWatch`.
It reacts to file system events (via `inotify`) to load new metafiles on
the spot, if you add the necessary configuration and activate it. This
way you have no delays at all, and no polling of watch directories in
short intervals, most often with no tangible result and just wasted CPU
cycles. Also, you can place the metafiles in arbitrary folders and
sub-folders, with just one configuration entry for the root folder to
watch. The queue is able to start items loaded via `inotify`, i.e. both
jobs can work together.

If you want to know about the gory details of the machinery behind this,
read `torque-custom-jobs`{.interpreted-text role="ref"}.

## Initial Setup

Before you start configuring the daemon, you have to install some
additional Python dependencies it needs to do its work, also depending
on what jobs you activate in your configuration. The following is how to
install the *full* set of dependencies:

``` shell
~/.local/pyroscope/bin/pip install -r ~/.local/pyroscope/requirements-torque.txt
```

Watch out for any errors, since this installs several Python extensions
that *might* need some `*-dev` OS packages available that you don\'t
have on your machine.

The `pyrotorque` queue manager daemon relies on certain additions to
`rtorrent.rc`, these are included in the standard `pyrocore` includes
that you added when you followed the `setup`{.interpreted-text
role="doc"}. If for whatever reason you need to add these manually, the
file `~/.pyroscope/rtorrent.d/torque.rc.default` holds these settings.

The daemon itself is configured by an additional configuration file
`~/.pyroscope/torque.ini` containing the `[TORQUE]` section. Most
settings are already covered in `torque.ini.default`, including some
short explanation what each setting does. The next section shows how to
customize these defaults.

## Configuration {#torque-config}

### Minimal Example

The following is a **minimal** `~/.pyroscope/torque.ini` **configuration
example**, only changing a few values from the defaults to demonstrate
key features:

``` ini
# "pyrotorque" configuration file
#
# For details, see https://pyrocore.readthedocs.io/en/latest/advanced.html#torque-config
#

[TORQUE]
# Queue manager
job.queue.active            = True
job.queue.schedule          = second=*/5
job.queue.intermission      = 60
job.queue.downloading_max   = 3
job.queue.startable         = is_ignored=0 message= prio>0
        [ prio>2 OR [ NOT [ traits=audio kind_25=jpg,png,tif,bmp ] ] ]
job.queue.downloading       = [ prio>1 [ down>3 OR started<2i ] ]

# Tree watch (works together with the queue)
job.treewatch.active        = True
job.treewatch.load_mode     = start
job.treewatch.queued        = True
job.treewatch.path          = /var/torrent/watch
job.treewatch.cmd.nfo       = f.multicall=*.nfo,f.priority.set=2
job.treewatch.cmd.jpg       = f.multicall=*.jpg,f.priority.set=2
job.treewatch.cmd.png       = f.multicall=*.png,f.priority.set=2
job.treewatch.cmd.tif       = f.multicall=*.tif,f.priority.set=0
job.treewatch.cmd.target    = {{# set target path
    }}d.custom.set=targetdir,/var/torrent/done/{{label}}/{{relpath}}
```

Having a minimal configuration with just your changes is recommended, so
you get new defaults in later releases automatically.

See the [default
configuration](https://github.com/pyroscope/pyrocore/blob/master/src/pyrocore/data/config/torque.ini)
for **more parameters and what they mean**.

::: warning
::: title
Warning
:::

If the folder tree specified in the `path` setting overlaps with the
paths used in existing 'watch' schedules of `rtorrent.rc`, then please
either keep those paths apart, or disable those schedules (comment them
out), *before* activating tree watch.

Anything else will lead to confusing and inconsistent results.
:::

### Queue Settings Explained

In the above example for the `queue` job, `downloading_max` counts
started-but-incomplete items including those that ignore commands. Only
if there are fewer of these items in the client than that number, a new
item will be started. This is the queue\'s length and thus the most
important parameter.

The queue *never* stops any items, i.e. `downloading_max` is not
enforced and you can manually start more items than that if you want to.
That is also the reason items that should be under queue control must be
loaded in 'normal' mode, i.e. stopped.

Other queue parameters are the minimum number of items in
\'downloading\' state named `downloading_min`, which trumps
`start_at_once`, the maximum number of items to start in one run of the
job. Both default to `1`. Since the default schedule is `second=*/15`,
that means at most one item would be started every 15 seconds.

But that default is changed using the following two lines:

``` ini
job.queue.schedule          = second=*/5
job.queue.intermission      = 60
```

This makes the queue manager check more often whether there is something
startable, but prevents it from starting the next batch of items when
the last start was less than `intermission` seconds ago.

The `startable` condition (repeated below for reference) prevents
ignored items, ones having a non-empty message, and those with the
lowest priority from being started. Note that tree watch sets the
priority of items loaded in 'normal' mode to zero -- that `prio>0`
condition then excludes them from being started automatically some time
later, until you press `+` to increase that priority. You can also delay
not-yet-started items using the `-` key until the item has a priority of
zero (a/k/a `off`).

``` ini
job.queue.startable = is_ignored=0 message= prio>0
        [ prio>2 OR [ NOT [ traits=audio kind_25=jpg,png,tif,bmp ] ] ]
```

This sample condition also adds the extra hurdle that audio downloads
that don\'t stay below a 25% threshold regarding contained images are
**not** started automatically. *Unless* you raise the priority to 3
(`high`) using the `+` key, then they\'re fair game for the queue. Go do
all that with a plain rTorrent watch dir, in one line of configuration.

The parameter `sort_fields` is used to determinate in what order
startable items are handled. By default, higher priority items are
started first, and age is used within each priority class.

Above, it was mentioned `downloading_max` counts started-but-incomplete
items. The exact definition of that classification can be changed using
the `downloading` condition. A given condition is *always* extended with
`is_active=1 is_complete=0`, i.e. the started-but-incomplete
requirement.

``` ini
job.queue.downloading = [ prio>1 [ down>3 OR started<2i ] ]
```

In plain English, this example says we only count items that have a
normal or high priority, and transfer data or were started in the last 2
minutes. The priority check means you can 'hide' started items from the
queue by setting them to `low`, e.g. because they\'re awfully slow and
prevent your full bandwidth from being used.

The second part automatically ignores stalled items unless just started.
This prevents disk trashing when a big item is still creating its files
and thus has no data transfer -- it looks stalled, but we do not want
yet another item to be started and increasing disk I/O even more, so the
manager sees those idle but young items as occupying a slot in the
queue.

### Tree Watch Details

The `treewatch` job is set to co-operate with the queue as previously
explained, and load items as ready to be started (i.e. in stopped state,
but with normal priority). Any `load_mode` that is not either `start` or
`started` is considered as equivalent to `load.normal`.

``` ini
job.treewatch.active        = True
job.treewatch.load_mode     = start
job.treewatch.queued        = True
```

The configuration settings for `load_mode` and `queued` can also be
changed on a case-by-case basis. For that, one of the 'flags' `load`,
`start`, or `queued` has to appear in the path of the loaded metafile --
either as a folder name, or else delimited by dots in the file name.
These examples should help with understanding how to use that:

    ☛ load and start these, ignoring what 'load_mode' says
    …/tv/start/foo.torrent
    …/movies/foo.start.torrent

    ☛ just load these, ignoring what 'load_mode' says
    …/tv/load/foo.torrent
    …/movies/foo.load.torrent

    ☛ always queue these, using the configured 'load_mode'
    …/tv/queue/foo.torrent
    …/movies/foo.queue.torrent

Should you have both `start` and `load` in a path, then `start` wins.

`path` determines the root of the folder tree to watch for new metafiles
via registration with the `inotify` mechanism of Linux. That means they
are loaded milliseconds after they\'re written to disk, without any
excessive polling.

``` ini
job.treewatch.path          = /var/torrent/watch
```

You can provide more that one tree to watch, by separating the root
folders with `:`.

The `cmd.«name»` settings can be used to provide additional load
commands, executed during loading the new item, *before* it is started
(in case it is started at all). This is equivalent to the commands you
can append to a rTorrent `load.*` command. They\'re added in the
alphabetic order of their names.

``` ini
job.treewatch.cmd.nfo       = f.multicall=*.nfo,f.priority.set=2
job.treewatch.cmd.jpg       = f.multicall=*.jpg,f.priority.set=2
job.treewatch.cmd.png       = f.multicall=*.png,f.priority.set=2
job.treewatch.cmd.tif       = f.multicall=*.tif,f.priority.set=0
job.treewatch.cmd.target    = {{# set target path
    }}d.custom.set=targetdir,/var/torrent/done/{{label}}/{{relpath}}
```

The above example shows how to set any NFO files and JPG/PNG images to
high priority, and prevent downloading any TIF images by default.

Commands can be templates, see `tree-watch`{.interpreted-text
role="ref"} for further details on the `target` command.

::: note
::: title
Note
:::

In case no files are loaded after you activated tree watch, you can set
`trace_inotify` to `True` to get detailed logs of all file system events
as they are received.

Also keep in mind that for now, if you add metafiles while the
`pyrotorque` daemon is not running, you have to `touch` them manually
after you have restarted it to load them.
:::

### Testing Your Configuration

After having completed your configuration, you\'re ready to **test it,
by following these steps**:

1.  Execute `rm ~/.pyroscope/run/pyrotorque` to **prevent the watchdog
    from starting the manager** in the background.
2.  **Stop any running daemon** process using `pyrotorque --stop`, just
    in case.
3.  Run `pyrotorque --fg -v` in a terminal, this will **start the job
    scheduler in the foreground** with verbose logging directly to that
    terminal, exactly what you need to check out if your configuration
    does what you intended. It also helps you to understand what goes on
    \"under the hood\".
4.  If you applied **changes to your configuration**, stop the running
    scheduler by pressing CTRL-C, then **restart it**. Wash, rinse,
    repeat.
5.  Press CTRL-C for the last time and call `pyrotorque --status`, it
    should show that no daemon process is running.
6.  Execute `touch ~/.pyroscope/run/pyrotorque` --- this does **create
    the guard file again**, which must always exist if you want
    `pyrotorque` to run in the background (otherwise you\'ll just get an
    error message on the console or in the log, if you try to launch
    it).
7.  **Wait up to 300 seconds**, and if your *rTorrent* configuration has
    the `pyro_watchdog` schedule as it should have,
    `pyrotorque --status` will show that a daemon process was
    automatically started by that *rTorrent* schedule.
8.  Enjoy, and **check** `~/.pyroscope/log/torque.log` for feedback from
    the daemon process.

If you want to restart the daemon running in the background immediately,
e.g. to **reload** `torque.ini` or after a software update, use
`pyrotorque --cron --restart`.

## Built-in Jobs

The `QueueManager` is just one kind of job that can be run by
`pyrotorque`. It has an embedded scheduler that can run any number of
additional jobs, the following sections explain the built-in ones. Since
these jobs can be loaded from any available Python package, you can also
easily `write your own <torque-custom-jobs>`{.interpreted-text
role="ref"}.

Jobs and their configuration are added in the `[TORQUE]` section, by
providing at least the parameters `job.«NAME».handler` and
`job.«NAME».schedule`. Depending on the handler, additional parameters
can/must be provided (see below for a list of built-in handlers and what
they do).

Details on the `schedule` parameter can be found
[here](https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html).
Multiple fields must be separated by spaces, so if a field value
contains a space, it must be quoted, e.g. `hour=12 "day=3rd sun"`. The
`handler` parameter tells the system where to look for the job
implementation, see the handler descriptions below for the correct
values.

**QueueManager**

`pyrocore.torrent.queue:QueueManager` manages queued downloads (i.e.
starts them in a controlled manner), it is described in detail
`further up on this page <torque-config>`{.interpreted-text role="ref"}.

**TreeWatch** (beta, not feature-complete)

`pyrocore.torrent.watch:TreeWatch` watches a folder tree, which can be
nested arbitrarily. Loading of new `.torrent` files is immediate (using
`libnotify`).

**TODO** Each sub-directory can contain a `watch.ini` configuration file
for parameters like whether to start new items immediately, and for
overriding the completion path.

See the explanation of the example configuration above and
`tree-watch`{.interpreted-text role="ref"} for further details.

**EngineStats**

`pyrocore.torrent.jobs:EngineStats` runs once per minute, checks the
connection to rTorrent, and logs some statistical information.

You can change it to run only hourly by adding this to the
configuration: `job.connstats.schedule      = hour=*`

# Using the Tree Watch Job

## Introduction

As mentioned in `QueueManager`{.interpreted-text role="ref"}, commands
configured to be executed during item loading can be templates. This can
be used to support all sorts of tricks, the most common ones are
explained here, including fully dynamic completion moving. If the
following explanation of the inner workings is too technical and nerdy
for you, skip to the `tree-watch-examples`{.interpreted-text role="ref"}
section below, and just adapt one of the prepared use cases to your
setup.

So how does this work? When a `.torrent` file is notified for loading
via `inotify`, it\'s parsed and contained data is put into variables
that can be used in the command templates. In order to get an idea what
variables are available, you can dump the templating namespace for a
metafile to the console, by calling the `watch` job directly.

Consider this example:

``` shell
$ date >example.dat
$ mktor -q example.dat http://tracker.example.com/
$ python-pyrocore -m pyrocore.torrent.watch -v example.dat.torrent
…
DEBUG    Tree watcher created with config Bunch(active=False, …
    cmd.target='{{# set target path\n}}d.custom.set=targetdir,/var/torrent/done/{{label}}/{{relpath}}',
    dry_run=True, handler='pyrocore.torrent.watch:TreeWatch', job_name='treewatch',
    load_mode='start', path='/var/torrent', queued='True', quiet='False', schedule='hour=*')
DEBUG    custom commands = {'target': <Template 2d01990 name=None>, 'nfo': f.multicall=*.nfo,f.set_priority=2, …}
INFO     Templating values are:
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
    rTorrent attribute to the completion path (which can then be used in
    a typical `event.download.finished` handler), using the `relpath`
    variable which is obtained from the full `.torrent` path, relative
    to the watch dir root.

2.  all kinds of other information is made available, like the
    torrent\'s info hash and the tracker alias; thus you can write
    conditional templates based on tracker, or use the tracker name in a
    completion path.

3.  for certain types of downloads, `traits` provides parsed information
    to build specific target paths, e.g. for the
    `Pioneer.One.S01E06.720p.x264-VODO` TV episode, you\'ll get this:

    ``` ini
    label='tv/mkv'
    traits=Bunch(aspect=None, codec='x264', episode='06', extension=None, format='720p',
        group='VODO', kind='tv', pattern='Normal TV Episodes', release=None,
        release_tags=None, season='01', show='Pioneer.One', sound=None, title=None)
    ```

## Tree Watch Examples

::: {.contents local=""}
:::

### Completion Moving

Since the templating namespace automatically includes the path of a
loaded `.torrent` file relative to the watch root (in `relpath`, see
above example namespace output and the config example further down), you
can set the \"move on completion\" target using that value.

``` ini
job.treewatch.cmd.target    = {{# set target path
    }}d.custom.set=targetdir,/var/torrent/done/{{label}}/{{relpath}}
```

Note that this still needs a typical completion event handler that takes
the custom variable that is set, and moves the data based on its value.

### Tree Watch with Sorting

This example adds a *second* job for a `sorted` tree that directly saves
the data into a path based on the loaded metafile\'s location.

``` ini
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
metafile as usual), and it won\'t start by itself.

Also, paths containing `music` use the metafile\'s basename as the data
directory, and metafiles recognized as TV content get separated into
show directories.
