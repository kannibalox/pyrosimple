---
title: Migrating from pyroscope
---
# Migrating from pyroscope

## Configuration

* The configuration file is located in a new location by default (`~/.config/pyrosimple/config.toml`), and uses a new format. Although the settings name have remained mostly the same, it is recommended to manually copy settings over to the new format.

## Common CLI

* Logging has been overhauled. `--cron` is now an alias for `--quiet`. All logging goes to stderr.

## `rtcontrol`

* Multiple actions flags are allowed, and the order in which they are specified is the order in which they are executed. Previously, only some combinations were allowed, and order did not matter.
* The `--anneal` flag has been removed. Use core Linux utilites (e.g. `sort` and `uniq`) instead.
* Matching an empty string with a blank value (e.g. `message=`) will no longer work as expected. Use a an empty quotes instead: `message=\"\"`.
* String matching is now case-sensitive by default. To use case-insensitive matching, use a regex with the `i` flag, e.g. `name=/UbUnTu.*/i`

### Templating

* Tempita has been replaced with [Jinja2](https://jinja.palletsprojects.com/en/3.0.x/templates/). The syntax is similar
  but not equivalent.
  ```
  # Old
  rtcontrol // -o '{{ if d.is_multi_file }}Multi-file path: {{ else }}Single file: {{ endif }}{{item.directory}}'
  # New
  rtcontrol // -o '{% if d.is_multi_file %}Multi-file path: {% else %}Single file: {% endif %}{{item.directory}}'
  ```
* The native python formatting style has been removed. Use the jinja2 template instead.
  ```
  # Old
  rtcontrol // -o '%(size.sz)s %(name)s'
  # New
  rtcontrol // -o '{{item.size|sz}} {{item.name}}'
  ```

### `--exec`

* All commands now use the full name. As such, the `:` signifier no longer has any effect.
  ```
  # Old
  rtcontrol // --exec "directory.set={{item.directory}}/{{item.custom_target_folder}}"
  rtcontrol --exec ":event.download.finished=" loaded=-10i done=100
  # New
  rtcontrol // --exec "d.directory.set={{item.directory}}/{{item.custom_target_folder}}"
  rtcontrol --exec "event.download.finished=" loaded=-10i done=100
  ```

## `rtxmlrpc`

* `-x, --xml, -r, --repr` have been removed. Use `-o <format>` to control the output format.
