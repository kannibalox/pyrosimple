# Changelog

## [Unreleased]

## [2.0.3] - 2022-09-28

### Fixed

- Report actual RPC stats in debug output
- Handle custom1, custom2, etc correctly

### Changed

- Unify `util.metafile` to perform most operations in a dict-like class

### Added

- New `shell` template filter

## [2.0.2] - 2022-09-14

### Fixed

- Validate simple output formatters against all jinja2 filters

## [2.0.0] - 2022-09-13

This release marks the break between pyrocore-compatible code and new pyrosimple code/behavior. The changes are too numerous
to list individually, but the following are some of the backwards-incompatible changes:

- Overhauled `rtcontrol`'s query parsing engine
- Python 2 support dropped
- New TOML configuration file

If you just want to use the pyrocore tools on python 3 without all the new features, you can use the `release-1.X` branch or the 1.X releases.
