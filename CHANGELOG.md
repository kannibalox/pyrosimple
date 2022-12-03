# Changelog

## [Unreleased]

### Fixed
- `rtcontrol`: Fix `-s *`

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

- https://github.com/kannibalox/pyrosimple/pull/11 `chtor`: Fix
  `--reannounce-all` without `--no-cross-seed`

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

[Unreleased]: https://github.com/kannibalox/pyrosimple/compare/v2.4.0...HEAD
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
