# Changelog

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
