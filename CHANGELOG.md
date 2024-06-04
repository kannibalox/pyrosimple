# Changelog

## [Unreleased]

## [2.14.0] - 2024-06-04

### Fixed
- `mktor`/`lstor`/`chtor`: No longer create the progress bar object at
  all if not enabled. This should improve non-interactive script
  usage.

### Added
- Explicit python 3.12 support
- `pyrotorque`: Add `preload_fields` to `TreeWatch` job, to allow
  fetching expensive-but-cacheable fields right after a successfully
  load.

### Changed
- The default prefetch fields have been reduced, in particular to no
  longer use `d.ratio`, which is a relatively expensive call for
  incomplete items.

## [2.13.0] - 2024-01-29

### *Breaking changes*
- New assignment syntax to allow more complex keys. This mainly
  effects mktor and chtor's `-s KEY=VAL` flag. This means the old
  syntax of `..` to escape periods in key names will no longer
  work. Use the new bracket syntax instead:
  ```bash
  # Old
  chtor -s info.with..period=foo <file>
  # New
  chtor -s 'info["with.period"]=foo' <file>
  ```

### Changed
- `lstor`: Torrents without an announce URL are no longer considered
  invalid, and can be displayed by `lstor`. This is primarily to
  support the listing of rTorrent's temporary torrent files generated
  from magnet
  links. [#61](https://github.com/kannibalox/pyrosimple/issues/61)
- `chtor`/`mktor`: Use a proper assignment syntax to allow setting complex keys and
  array keys
- `rtcontrol`: `--prio` now accepts strings as well as integers
  (0=off, 1=low, 2=normal, 3=high)

### Fixed
- Magnet files are now created with the correct key (`magnet-uri`) for
  rTorrent to load them.

### Added
- `lstor`: Add `--json` as alias for `--raw`

## [2.12.1] - 2023-12-12

### Changed
- Add `d.timestamp.last_xfer` as prefetch field for `last_xfer`

### Fixed
- Comparisons on some time fields [#60](https://github.com/kannibalox/pyrosimple/issues/60)

## [2.12.0] - 2023-10-30

### Fixed
- `rtcontrol`: `--cull`/`--purge` now clean up empty directories
  properly

### Added
- `chtor`/`mktor`/`lstor`: `--progress` flag to allow controlling
  hash check progress bar

### Changed
- The SSH transport now behaves more like the original pyroscope:
  - Allow for non-22 ports
  - Handle absolute paths similarly
  - Disable SSH pseudo-terminal allocation
  - Increase socat timeout to 5 seconds
- `lstor` refactoring:
  - `-o` now effects the output of `--raw`
  - `-o ""` now means "do not output any fields"
  - Data is hash checked *after* printing info
  - Do not halt immediately when validation fails, but set the exit
    code to `70` (failed hash checks return `65`)

## [2.11.4] - 2023-10-07

### Changed
- `lstor`: Now fails immediately when a piece mismatch occurs, and
  outputs the error to standard out instead of logging it.

### Fixed
- `chtor`: Fix error when combining `--fast-resume` and `-o`
- `pyroadmin`: Fix false negative when detecting methods on systems
  that implemented them in C++

## [2.11.3] - 2023-09-25

### Changed
- `pyrotorque`: `QueueManager` now has a default `matcher` setting of
  `is_complete=no is_ignored=no is_open=no message="" done=0`
- `pyrotorque`: The `args` paremeter for
  `pyrosimple.job.action:Action` now accepts non-string values.

## [2.11.2] - 2023-09-20

### Fixed
- `rtcontrol`: Make parent directories when moving/copying
- `rtcontrol`: Fix `-and-set` variants not doing anything

## [2.11.1] - 2023-09-12

### Fixed
- `lstor`/`mktor`/`chtor`: The progress bar no longer appears when
  `-q` is used
- `lstor`: Fix possible `ZeroDivisionError` when hashing small files
  on Windows
  ([#53](https://github.com/kannibalox/pyrosimple/issues/53))

## [2.11.0] - 2023-09-10

### Changed
- `chtor`: Improve handling of improper metafiles when `-V` is
  specified

### Added
- `lstor`: Support displaying hybrid v2 .torrent files. `rTorrent`
  doesn't support padding files yet, so this is mostly theoretical.
- `rtcontrol`: Add `label` and `custom1` as aliases for `custom_1`
- `rtcontrol`: Finalize flags for moving paths and optionally setting
  the directory: `--move`, `--move-and-set`, `--symlink`, etc...

### Fixed
- `rtcontrol`: The average in `--summary` no longer errors out under
  certain conditions
- `rtcontrol`: Fix debug logging, and avoid cleaning up parent
  directories for single file torrents with `--cull`/`--purge`
  ([#52](https://github.com/kannibalox/pyrosimple/issues/52))

## [2.10.2] - 2023-07-31

### Fixed
- Remove debugging statements

## [2.10.1] - 2023-07-28

### Fixed
- `rtcontrol`: Fix `--json` error

## [2.10.0] - 2023-07-24

### Added
- `pyrotorque`: Add the `--log-file` flag to allow controlling where
  the stdout/stdout are sent after detaching
- `pyrotorque`: Add dedicated `[TORQUE._settings]` key in
  `config.toml` to control settings such as the log level, pid file
  location, autoreload, etc.
- Allow parsing simple `cat` string replacements when auto-detecting
  the SCGI URL (e.g. `network.scgi.open_local=(cat,(cfg.rundir),"scgi.socket")`)
- `pyrotorque`: Allow adopting stale PID files (with the
  `--adopt-stale-pid-file` flag)

### Fixed
- `pyrotorque`: Check if pidfile can be successfully locked prior to
  forking

### Changed
- `rtcontrol`: Allow templating the `--move` flag

## [2.9.1] - 2023-07-09

### Fixed

- `rtcontrol`: `-V` was not working as expected
  (https://github.com/kannibalox/pyrosimple/issues/40)

## [2.9.0] - 2023-07-02

### Fixed
- `rtcontrol`: Under some circumstances, `~/.rtorrent.rc` would not be
  checked for a connection
- `mktor`: Don't strip characters after final `.` from auto-generated
  torrent name for directories
- `rtcontrol`: Allow more than two `OR`  conditions

### Changed
- `rtcontrol`: Output sub-multicall fields (e.g. `p_client_version`)
  in JSON format
- `rtcontrol`: Exact matches also match in patterns. E.G. previously
  `name="[ARCH] live.iso"` would not match an item of the exact same
  name, due to `[` and `]` being special characters in
  [fnmatch](https://docs.python.org/3/library/fnmatch.html)
- Expand `~` when set in `scgi_url`
  (https://github.com/kannibalox/pyrosimple/issues/34)

## [2.8.0] - 2023-04-29

### Fixed
- `pyroadmin`: Fix error when calling `config --create-config`
  (https://github.com/kannibalox/pyrosimple/pull/33 by @JohnFlowerful)

### Added
- Memoization helper function for expensive custom fields
- Add `PYRO_FORCE_JSONRPC_LOAD_RAW` env var to allow overriding
  JSON-RPC load behavior.

### Changed
- Simplify internal f.multicall setup to reduce size of calls
- Respect `ITEM_CACHE_EXPIRATION` for RPC calls (previously it was
  always set to the default of 5 seconds).

## [2.7.1] - 2023-04-09

### Changed
- `pyroadmin`: `config --check` now also checks if the methods
  necessary for timestamp fields (e.g. `completed`) exist.

### Fixed
- `rtcontrol`: Show a more useful error message when using `--from=<hash>`
  with a hash that doesn't exist
- Send assigned SCGI headers over unix sockets
- `chtor`: Fix `-o/--output-directory` (https://github.com/kannibalox/pyrosimple/issues/32)

## [2.7.0] - 2023-02-11

### Added
- `rtcontrol`: Add `f_METHOD`, `p_METHOD` and `t_METHOD` dynamic
  fields.

### Changed
- Move from settings `DynaConf` to `Box`. This should not have any
  impact on the documented usage, but will decrease CLI cold start times.

### Fixed
- Fix `pyroadmin config --create-rtorrent-rc` when the config files do
  not exist. (https://github.com/kannibalox/pyrosimple/pull/27 by
  @vamega)
- Fix inconsistent matching on TimeFilter fields (e.g. `completed`)
  (https://github.com/kannibalox/pyrosimple/issues/28)

## [2.6.1] - 2023-01-26

### Fixed
- Fixed error when logging actions

## [2.6.0] - 2023-01-15

### Fixed
- Properly set content-type headers for HTTP handler

### Changed
- `rtcontrol`: Allow handling more `d.*` commands with the `d_NAME`
  fields.
- `chtor`: Only modify existing files if changes have been made
- `chtor`: `--reannounce` now matches based on aliases/TLDs (which
  matches `--tracker`'s behavior)
- `rtcontrol`: Add `--erase` alias for `--delete`

### Added
- `chtor`: Added `--check-data` flag to allow checking data before
  making any changes, e.g. `chtor --check-data <dir> --fast-resume
  <dir>` to allow fully hash checking a torrent prior to it being
  added to rTorrent.
- `chtor`: Added `--diff` flag to show any changes being made. It can
  also be combined with `--dry-run` to preview changes.
- `chtor`: Added `--tracker/-T` flag to enable filtering by
  tracker. This also works with
  [aliases](https://kannibalox.github.io/pyrosimple/configuration/#aliases).

### Removed
- `chtor`: Removed `--no-ssl` flag.

## [2.5.4] - 2023-01-03

### Fixed
- Fix regression in properly translating `custom_1.._5` fields.

### Changed
- `pyrotorque`: For `RtorrentExporter`, scrape on the job schedule
  instead of the actual HTTP call. This helps prevent both slow scrapes
  from stacking up, and duplicate RPC calls when being scraped by
  multiple prometheuses.

## [2.5.3] - 2022-12-29

### Fixed
- `pyrotorque`: For `TreeWatch`, fix inotify masks

## [2.5.2] - 2022-12-29

### Added
- `pyroadmin config`: Add `--create-config` and `--create-rtorrent-rc`
  flags for setting up default config

### Fixed
- `rtcontrol`: Fix `--prio`
- `rtcontrol`: Allow spaces in regexes (e.g. `rtcontrol "message=/(not
  |un)registered/"` will work as expected now)
- `pyrotorque`: For `QueueManager`, allow using old configuration
  setting `sort_fields`
- Properly handle spaces in comma-separated field lists

## [2.5.1] - 2022-12-22

### Added
- `rtcontrol`: Added `d_<call name>` field for arbitrary RPC calls. As
  an example, to show the
  [`d.creation_date`](https://rtorrent-docs.readthedocs.io/en/latest/cmd-ref.html#term-d-creation-date)
  of all torrent with connected peers
  ([`d.peers_connected`](https://rtorrent-docs.readthedocs.io/en/latest/cmd-ref.html#term-d-peers-connected)),
  you can now run `rtcontrol d_peers_connected=1 -o
  d_creation_date`. Note that the built-in fields are still
  recommended due to the advanced filtering and output capabilities
  (currently all `d_<call name>` fields are treated as strings). There
  are also some commands that will work under the `d_<call name>`
  system, such as `d.skip.rate`.

### Fixed
- Dynamically generate timestamps during the filtering process. For
  example, a matcher created from `completed>1h` will still match as
  expected even a couple hours later.
- `chtor`: Fix `--fast-resume`
- `lstor`: Don't throw error on empty creation date

### Changed
- `lstor`: Error with non-zero return code when `--check-data` fails
- Mark package as typed

## [2.5.0] - 2022-12-10

### BREAKING CHANGES
- HTTP URLs will no longer automatically append `/RPC2` on the end if
  the path isn't there. This has been deprecated since 2.3.0.

### Changed
- `rtcontrol`: Certain floats will display less precision for better
  output (`<field>.raw` can still be used to get the real value).
- `rtcontrol`: Correctly detect fields from unnamed conditions
  combined with named ones (e.g. `// is_complete=no` would previously
  not prefetch `d.name`)

### Fixed
- `rtcontrol`: Fix `-s *`
- `rtcontrol`: Warn if fast query is enabled for a host without
  `d.multicall.filtered`
- `Metafile.hash_check()` and `Metafile.add_fast_resume()` now handle
  single file torrents the same way
  ([#24](https://github.com/kannibalox/pyrosimple/issues/24))
- `mktor`: Fix `-o/--output-filename`


## [2.4.0] - 2022-12-03

### Changed
- `pyrotorque`: Overhaul TreeWatch and log format

### Fixed
- `rtcontrol`: Correctly handle moving torrents via JSON-RPC

## [2.3.3] - 2022-11-20

### Fixed
- `rtcontrol`: Properly handle `--from=<hash>` multicalls
- Add safety check for d.timestamp.last_active

### Added
- `pyroadmin`: Add `config --dump-rc`

### Changed
- `pyrotorque`: Change log format to include the job name.

## [2.3.2] - 2022-11-05

### Fixed
- `rtcontrol`: Handle complex queries better (e.g. `[ seedtime>8d OR
  ratio>1 ] custom_1=TV` should work as expected now)
- `rtcontrol`: Fix prefiltering for globs which include regex-like
  characters
- `rtcontrol`: Make null durations only match on `<field>==0` as per
  pyrocore's behavior

## [2.3.1] - 2022-11-03

### Fixed
- `rtcontrol`: Handle multi-connection aliases properly

## [2.3.0] - 2022-11-03

### Deprecated
- In a future release, `/RPC2` will no longer be added to HTTP
  connections

### Changed
- Defer imports to improve loading times
  |        | mktor -h | lstor -h | rtcontrol -h | rtcontrol // -o '' |
  |--------|----------|----------|--------------|--------------------|
  | Before | 0.364s   | 0.377s   | 0.382s       | 0.469s             |
  | After  | 0.112s   | 0.098s   | 0.141s       | 0.384s             |
- `pyrotorque`: Change `max_downloading_traffic` to
  `downloading_traffic_max`, in order to match other setting names.

### Added
- `mktor`: Add flags for controlling min/max piece size, as well
  as specifying it manually

### Fixed
- Use all trackers when aggregating in example custom field code
  (credit goes to @kchiem: https://github.com/pyroscope/pyrocore/pull/105)
- `pyrotorque`: Allow using `startable` instead of `matcher` for QueueManager
- `pyrotorque`: Resolve connection aliases in job definitions and CLI

## [2.2.1] - 2022-10-24

### Fixed
- Fix inverse tag matching and prefiltering
  (https://github.com/kannibalox/pyrosimple/issues/13)
- Fix `kind_N` fields
  (https://github.com/kannibalox/pyrosimple/issues/14)
- Properly clean regexes for finding the prefiltering string, and
  account for unclean-able regexes

### Added
- `rtxmlrpc`: Re-implement `--repl`

## [2.2.0] - 2022-10-15

### Fixed
- Fix setting tags
  (https://github.com/kannibalox/pyrosimple/issues/12)

### Added
- `rtcontrol`/`rtxmlrpc`:
  - Basic tab completion
  - Optional `guessit_*` fields (requires guessit to be installed:
    `pip install guessit`)
- `pyrotorque`
  - New `ItemCommand` job
  - Allow overriding `scgi_url` for individual jobs

### Changed
- Warn if rTorrent doesn't support `string.contains_i` for fast
  queries

## [2.1.1] - 2022-09-24

### Fixed

- `chtor`: Fix `--reannounce-all` without `--no-cross-seed`
  (https://github.com/kannibalox/pyrosimple/pull/11 by 0xallie)

### Added

- Option to automatically reload pyrotorque if the config changes (off
  by default)

### Changed

- `views` and `tagged` now support fast queries

## [2.1.0] - 2022-09-20

### Added

- Re-enabled `last_xfer` and `active` fields
  - Added safety check for `last_xfer` if required method is not
    available
- Configuration option `item_cache_expiration` for more explicit
  control of the cache

### Fixed

- rtcontrol
  - `--json` will now display all known fields by default
  - `--throttle` works as intended
  - send string to interval calculations instead of object (effected
    `seedtime`, `leechtime`, `stopped`)
  - Fix pre-fetching for `views`

### Changed

- Show full stack traces for templating errors while using `--debug`

## [2.0.3] - 2022-09-18

### Fixed

- Report actual RPC stats in debug output
- Handle custom1, custom2, etc correctly

### Changed

- Unify `util.metafile` to perform most operations in a dict-like
  class

### Added

- New `shell` template filter

## [2.0.2] - 2022-09-14

### Fixed

- Validate simple output formatters against all Jinja2 filters

## [2.0.0] - 2022-09-13

This release marks the break between pyrocore-compatible code and new
pyrosimple code/behavior. The changes are too numerous to list
individually, but the following are some of the backwards-incompatible
changes:

- Overhauled `rtcontrol`'s query parsing engine
- Python 2 support dropped
- New TOML configuration file

If you just want to use the pyrocore tools on python 3 without all the
new features, you can use the `release-1.X` branch or the 1.X
releases.

[Unreleased]: https://github.com/kannibalox/pyrosimple/compare/v2.14.0...HEAD
[2.14.0]: https://github.com/kannibalox/pyrosimple/compare/v2.13.0...v2.14.0
[2.13.0]: https://github.com/kannibalox/pyrosimple/compare/v2.12.1...v2.13.0
[2.12.1]: https://github.com/kannibalox/pyrosimple/compare/v2.12.0...v2.12.1
[2.12.0]: https://github.com/kannibalox/pyrosimple/compare/v2.11.4...v2.12.0
[2.11.4]: https://github.com/kannibalox/pyrosimple/compare/v2.11.3...v2.11.4
[2.11.3]: https://github.com/kannibalox/pyrosimple/compare/v2.11.2...v2.11.3
[2.11.2]: https://github.com/kannibalox/pyrosimple/compare/v2.11.1...v2.11.2
[2.11.1]: https://github.com/kannibalox/pyrosimple/compare/v2.11.0...v2.11.1
[2.11.0]: https://github.com/kannibalox/pyrosimple/compare/v2.10.2...v2.11.0
[2.10.2]: https://github.com/kannibalox/pyrosimple/compare/v2.10.1...v2.10.2
[2.10.1]: https://github.com/kannibalox/pyrosimple/compare/v2.10.0...v2.10.1
[2.10.0]: https://github.com/kannibalox/pyrosimple/compare/v2.9.1...v2.10.0
[2.9.1]: https://github.com/kannibalox/pyrosimple/compare/v2.9.0...v2.9.1
[2.9.0]: https://github.com/kannibalox/pyrosimple/compare/v2.8.0...v2.9.0
[2.8.0]: https://github.com/kannibalox/pyrosimple/compare/v2.7.1...v2.8.0
[2.7.1]: https://github.com/kannibalox/pyrosimple/compare/v2.7.0...v2.7.1
[2.7.0]: https://github.com/kannibalox/pyrosimple/compare/v2.6.1...v2.7.0
[2.6.1]: https://github.com/kannibalox/pyrosimple/compare/v2.6.0...v2.6.1
[2.6.0]: https://github.com/kannibalox/pyrosimple/compare/v2.5.4...v2.6.0
[2.5.4]: https://github.com/kannibalox/pyrosimple/compare/v2.5.3...v2.5.4
[2.5.3]: https://github.com/kannibalox/pyrosimple/compare/v2.5.2...v2.5.3
[2.5.2]: https://github.com/kannibalox/pyrosimple/compare/v2.5.1...v2.5.2
[2.5.1]: https://github.com/kannibalox/pyrosimple/compare/v2.5.0...v2.5.1
[2.5.0]: https://github.com/kannibalox/pyrosimple/compare/v2.4.0...v2.5.0
[2.4.0]: https://github.com/kannibalox/pyrosimple/compare/v2.3.3...v2.4.0
[2.3.3]: https://github.com/kannibalox/pyrosimple/compare/v2.3.2...v2.3.3
[2.3.2]: https://github.com/kannibalox/pyrosimple/compare/v2.3.1...v2.3.2
[2.3.1]: https://github.com/kannibalox/pyrosimple/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/kannibalox/pyrosimple/compare/v2.2.1...v2.3.0
[2.2.1]: https://github.com/kannibalox/pyrosimple/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/kannibalox/pyrosimple/compare/v2.1.1...v2.2.0
[2.1.1]: https://github.com/kannibalox/pyrosimple/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/kannibalox/pyrosimple/compare/v2.0.3...v2.1.0
[2.0.3]: https://github.com/kannibalox/pyrosimple/compare/v2.0.2...v2.0.3
[2.0.2]: https://github.com/kannibalox/pyrosimple/compare/v2.0.0...v2.0.2
[2.0.0]: https://github.com/kannibalox/pyrosimple/releases/tag/v2.0.0
