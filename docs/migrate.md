---
title: Migrating from pyroscope
---
# Migrating from pyroscope

## Configuration

* The configuration file is located in a new location by default
  (`~/.config/pyrosimple/config.toml`), and uses a new
  format. Although the names have remained mostly the same, it is
  recommended to manually copy settings over to the new format.

## Common CLI options

* Logging has been overhauled. `--cron` is now an alias for
  `--quiet`. All logging goes to stderr.
* `--config-dir` and `--config-file` have been removed. Set the
  `PYRO_CONF` environment variable use a non-default config file.
* `-D` has been removed. Use an environment variable to override
  specific parts of the configuration instead.
  ```bash
  # Old
  rtcontrol -D rtorrent_rc=/etc/rtorrent/rtorrent.rc //
  # New
  PYRO_RTORRENT_RC=/etc/rtorrent/rtorrent.rc rtcontrol //
  ```

## `rtxmlrpc`

* `-x, --xml, -r, --repr` for XML output is no longer available. See
  `--output <format>` for the new options.
* REPL mode no longer triggers automatically with 0 arguments. To
  enter it, use the `--repl` flag.

## `pyroadmin`

`pyroadmin` has been completely rebuilt. See `pyroadmin --help` for
available utilities.

## `rtcontrol`

* Multiple actions flags are allowed, and the order in which they are
  specified is the order in which they are executed. Previously, only
  some combinations were allowed, and order did not matter. See `rtcontrol --help`
  for the list of flags which are considered "actions".
  ```bash
  # Old
  rtcontrol // --stop
  rtcontrol // --custom foo=bar --flush
  rtcontrol // --custom baz=hkk --flush
  rtcontrol // --start
  # New
  rtcontrol // --stop --custom foo=bar --custom baz=hkk --flush --start
  ```
* The `--anneal` flag has been removed. Use core Linux utilities
  (e.g. `sort` and `uniq`) instead.
* Matching an empty string with a blank value (e.g. `message=`) will
  no longer work as expected. Use escaped quotes instead:
  `message=\"\"`.
* String matching is now case-sensitive by default. To use
  case-insensitive matching, use a regex with the `i` flag,
  e.g. `name=/UbUnTu.*/i`
* Relative times (e.g. `2d3m`) are now case-sensitive.

### Templating

* Tempita has been replaced with
  [Jinja2](https://jinja.palletsprojects.com/en/3.0.x/templates/). The
  syntax is similar but not equivalent.
  ```bash
  # Old
  rtcontrol // -o '{{ if d.is_multi_file }}Multi-file path: {{ else }}Single file: {{ endif }}{{item.directory}}'
  # New
  rtcontrol // -o '{% if d.is_multi_file %}Multi-file path: {% else %}Single file: {% endif %}{{item.directory}}'
  ```
* The string interpolation format style has been removed. Use the
  Jinja2 template instead.
  ```bash
  # Old
  rtcontrol // -o '%(size.sz)s %(name)s'
  # New
  rtcontrol // -o '{{item.size|sz}} {{item.name}}'
  ```

### `--exec`

* All commands now use the full name. As such, the `:` signifier no
  longer has any effect.
  ```bash
  # Old
  rtcontrol // --exec "directory.set={{item.directory}}/{{item.custom_target_folder}}"
  rtcontrol --exec ":event.download.finished=" loaded=-10i done=100
  # New
  rtcontrol // --exec "d.directory.set={{item.directory}}/{{item.custom_target_folder}}"
  rtcontrol --exec "event.download.finished=" loaded=-10i done=100
  ```

## `pyrotorque`

* All job handlers have been moved under the `pyrosimple.job`
  submodule. Specifically, `pyrocore.torrent.watch:QueueManager` is
  now `pyrosimple.job.queue:QueueManager` and
  `pyrocore.torrent.watch:TreeWatch` is now
  `pyrosimple.job.watch:TreeWatch`
* `TreeWatch`: The `queued` setting no longer has any effect. Use the
  following configuration to achieve the same effect if desired:
  ```toml
  [TORQUE.watch]
  handler = "pyrocore.job.watch:TreeWatch"
  # ...other settings...
  cmd_queue = "d.priority.set=0"
  ```
## `chtor`

* The `--no-ssl` flag has been removed. Manually specifying a non-SSL
  announce still works as expected.

## `hashcheck`

* This command has been removed. Use `lstor --check-data <path>` instead.

## `rtmv`

* This command has been temporarily removed. See [this discussion](https://github.com/kannibalox/pyrosimple/discussions/35)
  for more information, and a way to run the legacy conversion of the
  command.
