---
title: Advanced Features
---

!!! note
    Using these features requires some knowledge in the area of Linux,
    Bash, and Python, but they enable you to customize your setup even
    further and handle very specific use-cases.

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

Here's a practical example for using `--spawn`, it copies all your
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
item's data, plus a small part of the infohash to make these names
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
`output-templates`{.interpreted-text role="ref"} beforehand, it's
assumed here that you do.

### Repairing Stuck Items

Let's start with an easy example of using `--exec`, where no templating
is needed:

``` bash
rtcontrol --exec 'd.stop= ; d.close= ; f.multicall=,f.set_create_queued=0,f.set_resize_queued=0 ; d.check_hash=' \
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
rtcontrol --exec "event.download.finished=" 'loaded<10m' is_complete=y
```

The `:` prefix prevents `rtcontrol` from assuming this is a `d.` item
command.

Make sure that the registered handlers do not have adverse effects when
called repeatedly, i.e. know what you're doing. The handlers for an
event can be listed like so:

``` bash
rtxmlrpc --output-format repr method.get '' event.download.finished
```

### Relocating Download Data

The most simple variant of changing the download path is setting a new
fixed location for all selected items, as follows:

``` bash
rtcontrol --exec 'd.directory_base.set="/mnt/data/new/path"' directory=/mnt/data/old/path
```

This replaces the location of items stored at `/mnt/data/old/path` with
a new path. But to be really useful, we'd want to shift *any* path
under a given base directory to a new location -- the next command does
this by using templating and calculating the new path based on the old
one:

``` bash
rtcontrol \
    --exec 'd.directory_base.set="{{item.directory|subst("^/mnt/data/","/var/data/")}}" ; >d.directory=' \
    path=/mnt/data/\*
```

This selects any item stored under `/mnt/data` and relocates it to the
new base directory `/var/data`. Fields of an item can be used via a
`item.‹field-name›` reference. Adding `>d.directory=` prints the new
location to the console -- a semicolon with spaces on both sides
delimits several commands, and the `>` prints the result of a XMLRPC
command.

The `move-data`{.interpreted-text role="ref"} section has more on how to
also move the data on disk, in addition to changing the location in
rTorrent's session as shown here.

### Making Shared Data Paths Unique

Another example regarding data paths is this:

``` bash
rtcontrol --from stopped // --exec 'directory.set={{item.directory}}-{{item.hash}}'
```

That command ensures that items that would download into the same path
get a unique name by appending the info hash, and assumes those items
weren't started yet (i.e. added via `load.normal`).

### Changing Announce URLs in Bulk

The next example replaces an active announce URL with a new one, which
is necessary after a domain or passkey change. Compared to other methods
like using `sed` on the files in your session directory, this does not
require a client restart, and is also safer (the `sed` approach can
easily make your session files unusable). This disables all old announce
URLs in group 0 using a `t.multicall`, and then adds a new one:

``` bash
rtcontrol \
    --exec 't.multicall=0,t.disable= ; d.tracker.insert=0,"http://new.example.com/announce" ; d.save_full_session=' \
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
