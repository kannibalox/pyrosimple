---
title: Configuration
---

# Configuration

The configuration file for pyrosimple is lives in `$HOME/.config/pyrosimple/config.toml`. If you've
never used TOML files before, it's worth taking a quick look at the [documentation](https://toml.io/),
but basically each section starts with a `[SECTION_NAME]` followed by keys and values.

Here is a basic example of what your file could look like:
```toml
rtorrent_rc = "~/.rtorrent.rc"
fast_query = 0
[FORMATS]
action = '{{now|iso}} {{action}}\t {{d.name}} {{d.alias}}'
[ALIASES]
Ubuntu = ["ubuntu.com"]
```

If you'd like to use a file other than the default, use the `PYRO_CONF` environment variable:
```bash
PYRO_CONF=/tmp/config.toml rtxmlrpc system.hostname
```
Similar environment variables can be used to override individual parts of the configuration file:
```bash
PYRO_RTORRENT_RC=/etc/rtorrent/rtorrent.rc PYRO_FAST_QUERY=0 rtcontrol //
```

## Reference

### Top-level section

These entries in at the top of the file without a section name
contain the most basic configuration settings for pyrosimple.

#### `rtorrent_rc`

Defaults to `~/.rtorrent.rc`.

This tells pyrosimple where to look for the rtorrent config file. It's mainly
needed in order to automatically figure out where the SCGI port/file is listening,
but may have other uses in the future.

####  `scgi_url`

If you'd prefer to manually set the SCGI URL, you can use this value to do so. If it's
unset, pyrosimple will use the `rtorrent_rc` settings to automatically figure it out,
but will raise an error if it's unable to do so.

#### `sort_fields`

Defaults to `name,hash`.

Sets the default sort order for output in `rtcontrol`.

#### `mktor_ignore`

Defaults to `["core", "CVS", ".*", "*~", "*.swp", "*.tmp", "*.bak", "[Tt]humbs.db", "[Dd]esktop.ini", "ehthumbs_vista.db"]`

This allows overriding the list of temporary/hidden files `mktor` will ignore when creating torrents.

#### `fast_query`

Defaults to `0` (disabled).

See [query optimization](experimental.md#query-optimization) for more information.

### TORQUE

This section is reserved for `pyrotorque`. See its [user guide](/usage-pyrotorque/) for more information.

### FORMATS

Example:
```toml
# Example
[FORMATS]
default = '{%set ESC = "\x1B" %}{%if d.down > 0%}{{ESC+"[1m"}}{%endif%}{%if d.is_open%}O{%else%} {%endif%}{%if  d.is_active%}A{%else%} {%endif%}{%if not d.is_complete%}{{ESC+"[36m"}}{{ "{:>3}".format(d.done | round | int) }}{{ESC+"[0m"}}{%else%}  D{%endif%} {{"{:>10}".format(d.size | filesizeformat(True))}} {%if d.message%}{{ESC+"[31m"}}{%endif%} {{d.alias.rjust(3)}}{{ESC+"[0m"}} {%if d.down > 0%}{{ESC+"[1m"}}{%endif%}{{d.name}}{{ESC+"[0m"}}'
filelist = '{% for f in d.files%}{{d.realpath}}{% if d.is_multi_file %}/{{f.path}}{% endif %}{% if loop.index != loop.length %}\n{% endif %}{% endfor %}'
action = '{{now|iso}} {{action}}\t {{d.name}} {{d.alias}}'
```

Allows defining Jinja2 templates for use with `rtcontrol`.

```bash
rtcontrol is_completed=yes -o filelist
```

Note that any names defined here will override field names in the `-o` simple format, so make sure there
are no conflicts.

### ALIASES

```toml
# Example with some common trackers
[ALIASES]
PBT     = ["tracker.publicbt.com", "http://tracker.publicbt.com:80/announce",
          "udp://tracker.publicbt.com:80/announce"]
PDT     = ["http://files2.publicdomaintorrents.com/bt/announce.php"]
ArchOrg = ["http://bt1.archive.org:6969/announce",
          "http://bt2.archive.org:6969/announce"]
OBT     = ["http://tracker.openbittorrent.com:80/announce",
          "udp://tracker.openbittorrent.com:80/announce"]
Debian  = ["http://bttracker.debian.org:6969/announce"]
Linux   = ["http://linuxtracker.org:2710/"]
```

This section allows for setting any number of tracker aliases for use with `rtcontrol`'s
"alias" field, and when creating torrents with `mktor`.


### CONNECTIONS

```toml
# Example
[CONNECTIONS]
local = "~/rtorrent/.scgi_local"
remote_scgi = "scgi://example.com:9000"
remote_https = "https://example.com/RPC2"
```

!!! Note
    For HTTP(S) connections, it's important to either explicitly provide the path (e.g. `https://example.com/RPC2`) or leave it off entirely
    (e.g. `https://example.com`). `https://example.com/` will not work for most setups.

`rtmlxrpc`, `rtcontrol` and `pyrotorque` accept a `-U`/`--url` flag to provide the `scgi_url` directly when working with remote machines:
```bash
rtxmlrpc -U "~/rtorrent/.scgi_local" system.hostname
```

Once defined, the short name can be used instead:
```bash
rtxmlrpc -U local system.hostname
```
