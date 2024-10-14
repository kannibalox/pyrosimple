---
title: Configuration
---

# Configuration

The configuration file for pyrosimple is lives in
`$HOME/.config/pyrosimple/config.toml`. If you've
never used TOML files before, it's worth taking a quick look at the
[TOML documentation](https://toml.io/),
but basically each section starts with a `[SECTION_NAME]` followed by
keys and values.

Here is a basic example of what your file could look like:
```toml
rtorrent_rc = "~/.rtorrent.rc"
fast_query = 1
[FORMATS]
action = '{{now|iso}} {{action}}\t {{d.name}} {{d.alias}}'
[ALIASES]
Ubuntu = ["ubuntu.com"]
```

If you'd like to use a file other than the default, use the
`PYRO_CONF` environment variable:
```bash
PYRO_CONF=/tmp/config.toml rtxmlrpc system.hostname
```
Similar environment variables can be used to override individual parts
of the configuration file:
```bash
PYRO_RTORRENT_RC=/etc/rtorrent/rtorrent.rc PYRO_FAST_QUERY=0 rtcontrol //
```
The equivalent environment variable will be shown in parentheses next
to the config name below for reference.

## Reference

### Top-level section

These entries in at the top of the file without a section name
contain the most basic configuration settings for pyrosimple.

#### `rtorrent_rc` (`PYRO_RTORRENT_RC`)

Defaults to `~/.rtorrent.rc`.

This tells pyrosimple where to look for the rTorrent config file. It's
mainly needed in order to automatically figure out where the SCGI
port/file is listening, but may have other uses in the future.

####  `scgi_url` (`PYRO_SCGI_URL`)

Defaults to being unset.

If you'd prefer to manually set the SCGI URL, you can use this value
to do so. When unset, pyrosimple will use the `rtorrent_rc` settings
to automatically figure it out, but will raise an error if it's unable
to find any hints.

#### `sort_fields` (`PYRO_SORT_FIELDS`)

Defaults to `name,hash`.

Sets the default sort order for output in `rtcontrol`.

#### `mktor_ignore`

Defaults to `["core", "CVS", ".*", "*~", "*.swp", "*.tmp", "*.bak", "[Tt]humbs.db", "[Dd]esktop.ini", "ehthumbs_vista.db"]`

This allows overriding the list of temporary/hidden files `mktor` will
ignore when creating torrents.

#### `fast_query` (`PYRO_FAST_QUERY`)

Defaults to `0` (disabled).

See [query optimization](experimental.md#query-optimization) for more
information.

#### `safety_checks_enabled` (`PYRO_SAFETY_CHECKS_ENABLED`)

Defaults to `True`.

Several safety checks exist to provide more useful error message in
cases such as missing methods/fields. In most cases this should have
no impact other than an extra call to rtorrent's `system.listMethods`,
but disabling these checks may be useful if you'd like to speed up
command runs.

#### `item_cache_expiration` (`PYRO_ITEM_CACHE_EXPIRATION`)

Defaults to `5.0`.

The number of seconds to keep cached information for each item. The
default aims to strike reasonable balance between reducing RPC calls
while avoiding stale data.  `0` makes the process cache all
information forever, while `-1` disables the cache entirely.

### TORQUE

This section is reserved for `pyrotorque`. See its
[user guide](usage-pyrotorque.md) for more information.

### FORMATS

Allows defining Jinja2 templates for use with `rtcontrol`.

Example:
```toml
[FORMATS]
default = '{%set ESC = "\x1B" %}{%if d.down > 0%}{{ESC+"[1m"}}{%endif%}{%if d.is_open%}O{%else%} {%endif%}{%if d.is_active%}A{%else%} {%endif%}{%if not d.is_complete%}{{ESC+"[36m"}}{{ "{:>3}".format(d.done | round | int) }}{{ESC+"[0m"}}{%else%}  D{%endif%} {{"{:>10}".format(d.size | filesizeformat(True))}} {%if d.message%}{{ESC+"[31m"}}{%endif%} {{d.alias.rjust(3)}}{{ESC+"[0m"}} {%if d.down > 0%}{{ESC+"[1m"}}{%endif%}{{d.name}}{{ESC+"[0m"}}'
filelist = '{% for f in d.files%}{{d.realpath}}{% if d.is_multi_file %}/{{f.path}}{% endif %}{% if loop.index != loop.length %}\n{% endif %}{% endfor %}'
action = '{{now|iso}} {{action}}\t {{d.name}} {{d.alias}}'
```

```bash
rtcontrol is_completed=yes -o filelist
```

Note that any names defined here will override field names in the `-o`
simple format, so make sure there are no conflicts.

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

This section allows for setting any number of tracker aliases for use
with `rtcontrol`'s "alias" field, and when creating torrents with
`mktor`.

!!! note
    `rtcontrol` will cache alias information inside rTorrent custom keys
    in order to speed up commands. To clear and then repopulate the cache,
    run the following commands:
    
    ```bash
    rtcontrol --custom memo_alias= // -o hash # Clear the `memo_alias` custom key
    rtcontrol // -o alias                     # Force rtcontrol to immediate refill the key
    ```


### CONNECTIONS

```toml
# Example
[CONNECTIONS]
local = "~/rtorrent/.scgi_local"
remote_scgi = "scgi://example.com:9000"
remote_https = "https://example.com/RPC2"
```

`rtmlxrpc`, `rtcontrol` and `pyrotorque` accept a `-U`/`--url` flag to
provide the `scgi_url` directly when working with remote machines:
```bash
rtxmlrpc -U "~/rtorrent/.scgi_local" system.hostname
```

Once defined, the short name can be used instead:
```bash
rtxmlrpc -U local system.hostname
```
