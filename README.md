# pyrosimple

![GitHub Workflow Status](https://img.shields.io/github/workflow/status/kannibalox/pyrosimple/Pylint)
![PyPI](https://img.shields.io/pypi/v/pyrosimple)
![PyPI -	Python Version](https://img.shields.io/pypi/pyversions/pyrosimple)

A simplified and python-3 oriented version of the [pyrocore tools](https://github.com/pyroscope/pyrocore), for working with the [rTorrent client](https://github.com/rakshasa/rtorrent).

## Installation

```bash
pip install pyrosimple
```

Usage is pretty much the same as regular pyroscope: https://github.com/pyroscope/pyrocore/blob/master/README.md

## What's the point of this?

I needed something simpler for use with personal tools, and this allows me to keep the code base *mostly* compatible while
dropping more experimental features. There are also several changes that aren't easily suitable for upstream incorporation.

## Significant differences from pyrocore

The following lists are not exhaustive, and don't cover many of the internal improvements and refactoring.

- Only supports python 3 and rtorrent 0.9.8 (0.9.6/0.9.7 should still work, just not officially supported)
- Simpler poetry-based build/install system
- Everything in one package (no separate pyrobase)
  - Use external lib for bencode

### Added
- Jinja2 templatiing if package is present (tempita's use of eval can chew up a surprising amount of cpu)
- Support for JSON-RPC (only implemented by https://github.com/jesec/rtorrent)
- pyrotorque job to move torrents between hosts
- pyrotorque job to move torrent paths

### Removed/deprecated
- the `rtsweep`, `rtmv`, and `rtevent` commands
- `pyrotorque`'s guard file, influxdb job and web server
- Connecting via SSH (planned to be re-added)

### Changed
- `rtxmlrpc`'s `--raw` now outputs JSON
