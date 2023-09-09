---
title: rtcontrol Usage
---

# rtcontrol

`rtcontrol` is one of the most flexible tools in the pyrosimple arsenal,
which also means it can become very complex very quickly.

`rtcontrol` maps rTorrent attributes to fields, which are a python-oriented
way to represent the attributes. You can see the list of supported fields
by running `rtcontrol --help-fields`.

## Filter Conditions

In order for `rtcontrol` to do anything, it first needs a filter
condition that will tell it which torrents it should perform work
against. Filters take the form of a field, operator and value, which
will look familiar if you've dealt with any kind of programming or
scripting.

```none
size>8G
loaded<2d5h
name=ubuntu-server-amd64-22.04.iso
```

If the field and operator are omitted, they are assumed to be `name`
and `=` respectively. This means the following filters are exactly the
same:

```none
ubuntu-server-amd64-22.04.iso
name=ubuntu-server-amd64-22.04.iso
```

If multiple filters are specified, torrents must match against all of
them. The special keyword `OR` can be used to override that behavior,
and change it so that only one of the filters have to match:

```none
size<=4G name!=ubuntu-server-amd64-22.04.iso
name=/ubuntu/ OR name=/debian/
```

`[` and `]` can be used to group filters, and `NOT` or `!` can be used to invert groups:

```none
! [ size>700m size<=1400m ]
name=arch-* OR [ alias=Ubuntu loaded>1w ]
```

!!! note
    Since many characters like `!` or `<` have special meanings in the
    shell, they will most likely need to be quoted or escaped when
    actually used on the command line.
    
    ```
    rtcontrol 'size>700m' 'size<=1400m'
    ```
    
    Entire queries can also be quoted without any problems:
    
    ```
    rtcontrol 'size>700m size<=1400m'
    ```
    

Many fields allow for special parsing of the value to support more complicated filters:

* strings (e.g. `name`, `alias`)
    * By default, strings are matched using [shell-style wildcards](https://docs.python.org/3/library/fnmatch.html). This means
      that to search for a substring instead of an exact match, you should use an expression like `*ubuntu*`.  
      Example: `arch-linux-*`
    * If the value starts and ends with `/`, the value is treated as a
      [regex](https://docs.python.org/3/library/re.html?highlight=re#regular-expression-syntax),
      which allows for more complex expressions than just
      wildcards. Note that the whole string does not need to match;
      use `^` and `$` to enforce that behavior.  
      Examples: `/.*/`, `/^ubuntu-.+-server-.*/`
* numbers (e.g. `size`, `xfer`)
    * Byte number fields like `size` allow for suffixes to denote the size.  
      Example: `5g`, `64m`
* time (e.g. `loaded`, `completed`)
  Similar to bytes, time fields accept multiple shorthands for comparing time:
    * Time deltas in the form of `<num><unit>[<num><unit>...]`, where
    `unit` is a single letter to denote `y`ear, `M`onth, `w`eek,
    `d`day, `h`our, `m`inute or `s`second.  
      Examples: `3w22h`, `1y6M`
    * An exact date/time in a human-readable formate. Acceptable
      formats for the date are `YYYY-MM-DD`, `MM/DD/YYYY`,
      `DD.MM.YYYY`. To also include a `HH:MM` time, separate it from
      the date with a space or a `T`.  
      Examples: `04/15/2021`, `2022-03-15T14:50`
    * An absolute timestamp in [epoch time](https://en.wikipedia.org/wiki/Unix_time) format.  
      Example: `1652289156`
* tags (e.g. `tagged`, `views`)
    * Tags are work similarly to strings, but they do not support
      regexes, and use whitespace as delimiters. For example, if a
      torrent has the tags `active archive new`, the values `n*` and
      `archive` would both match.

## Output

By default, rtcontrol will use a predefined output template that
displays most relevant information, but allows for selecting specific
fields with the `-o`/`--output-format` flag.

The simplest way to use it is to simply specific a comma-separated
list of fields:

```bash
rtcontrol // -o alias,size,path
```

If you want to override the default formatting, rtcontrol provides a set of specifiers for quick
changes (see `rtcontrol --help-fields` for the list of available specifiers).

```bash
# Same command as above, but modify the path and size output
rtcontrol // -o alias,size.sz,path.pathbase
```

#### Jinja2

For more complex output, the
[Jinja2](https://palletsprojects.com/p/jinja/) library can be used.
It has support for much more complex formatting and logic than the
simple CSV output. See the
[official Jinja2 documentation](https://jinja.palletsprojects.com/en/3.1.x/templates/)
for everything it's capable of .


```bash
rtcontrol // -o '{{d.alias}}\t{{d.size|filesizeformat(binary=True)}}\t{{d.path|truncate(40)}}'
```

As your output templates get more complex, you can use the `TEMPLATES`
section in the configuration to set predefined templates, rather than
putting the whole string in the CLI every time. This is how the
`default` and `action` templates are defined. See the
[configuration file](configuration.md)
for more info.

## Actions

rtcontrol has many ways to effect torrent, including but not limited to:

* `--start`/`--stop`/`--delete`: starting/stopping/remove torrents
* `--cull`,`--purge`: remove torrents along with all or partial data
* `--custom KEY=VALUE`: setting custom values
* `--move`/`--move-and-set`: Move, and optionally set the directory
  after the move (similar flags also exist to copy, symlink, and
  hardlink)
* `--call`/`--spawn`: call a OS command/shell
* `-H`/`--hash-check`: trigger a hash check on torrents (equivalent to
  pressing `^R` in the UI)

See `rtcontrol --help` for a full list of actions. All action can be
dry-run with the `-n`/`--dry-run` flag. Many of the more dangerous
actions (e.g. `--cull`) will prompt before actually performing the
action. However, if you wish to enable prompting for all action, the
`-i`/`--interactive` will set that behavior for all
commands. Alternatively, if you don't want any prompts at all
(e.g. when running in a headless script), `--yes` will automatically
confirm all prompts.

When multiple actions are specified, rtcontrol will apply those
actions to each item in sequence.

### Executing commands

`rtcontrol` has two ways to execute OS commands:

* ``--spawn`` creates a new process with the command:
  ```bash
  # Update the mtime on all session files
  rtcontrol --spawn 'touch {{item.metafile}}' //
  ```
* If you need to use shell features (such as pipes or file
  redirection) in the command, use ``--call` instead:
  ```bash
  # Append the name of completed items to a file
  rtcontrol --call 'echo {{item.name|shell}} >> /tmp/names.txt' is_complete=yes
  ```
Most of the time `--spawn` will be enough, but `-call` exists as a handy shortcut.

To call rTorrent's RPC, use the `--exec` flag:
```bash
# These two commands do the same thing: start all torrents
rtxmlrpc d.multicall2 '' default d.start=
rtcontrol // --exec 'd.start='
```
Besides filtering, using rtcontrol instead of rtxmlrpc allows you to use formatting
in the same manner as `--spawn`/`--call`:
```bash
# Set all incomplete downloads to a dedicated directory, based on hash
rtcontrol is_active=no is_complete=no --exec 'd.directory_base.set=/tmp/downloads/{{item.hash}}'
```

## Examples

* `rtcontrol '*HDTV*'`  
  Find anything with "HDTV" in its name.
* `rtcontrol is_open=y is_active=n`  
  Find paused items.
* `rtcontrol alias=foo --close`  
  Close all torrents from a specific tracker.
* `rtcontrol -o size.sz // --summary`  
  Show the total size of all torrents.
* `rtcontrol -o filelist path=/mnt/tmp/\*`  
  List all files in rTorrent under a directory.
* `rtcontrol --start is_complete=yes is_active=no is_open=no`  
  Start all completed but inactive torrents.

### Filter examples

* `'*HDTV*'`:
    Anything with "HDTV" in its name

* `/s\d+e\d+/`:
    Anything with typical TV episode numbering in its name (regex match)

* `ratio=+1`:
    All downloads seeded to at least 1:1

* `xfer=+0`:
    All active torrents (transferring data)

* `up=+0` or `up\>0`:
    All seeding torrents (uploading data)

* `down=+0 down=-5k` or `down\>0 down\<=5k`:
    Slow torrents (downloading, but with < 5 KiB/s)

* `down=0 is_complete=no is_open=yes`:
    Stuck torrents

* `size=+4g`:
    Big stuff (DVD size or larger)

* `is_complete=no`:
    Incomplete downloads

* `is_open=y is_active=n`:
    Paused items

* `is_ghost=yes`:
    Torrents that have no data (were never started or lost their data)

* `alias=obt`:
    Torrents tracked by `openbittorrent.com` (see
    [configuration](configuration.md#aliases) on how to add aliases for
    trackers)

* `ratio=+1 realpath\!=/mnt/\*`:
    1:1 seeds not on a mounted path (i.e. likely on localhost)

* `completed=+2w`:
    Completed more than 2 weeks ago

* `tagged=:` or `tagged=\"\"`:
    Not tagged at all

* `tagged!=:`:
    Has at least one tag

* `tagged=foo,bar`:
    Tagged with "foo" or "bar" (*since v0.3.5*) — tags are white-space
    separated lists of names in the field `custom_tags`

* `tagged=:highlander`:
    *Only* tagged with "highlander" and nothing else

* `kind=flac,mp3`:
    Music downloads

* `files=sample/\*`:
    Items with a top-level `sample` folder

* `ratio=+2.5 OR seedtime=+1w`:
  Items seeded to 5:2 **or** for more than a week

* `alias=foo [ ratio=+2.5 OR seedtime=+7d ]`:
  The same as above, but for one tracker only

* `traits=avi traits=tv,movies`:
  TV or movies in AVI containers

* `custom_1!=?*`:
  matches any torrent without a rutorrent label
  
* `custom_1==*`:
  matches any torrent with or without a rutorrent label
