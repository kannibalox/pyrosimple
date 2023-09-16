#!/bin/bash
set -eu
poetry check
prev_version="$(poetry version -s --no-ansi)"
poetry version "$1"
new_version="$(poetry version -s --no-ansi)"

sed -i -e "/## \[Unreleased\]/a \\\n## [${new_version}] - $(date +%Y-%m-%d)" \
    -e "s|\[Unreleased\]: .*|[Unreleased]: https://github.com/kannibalox/pyrosimple/compare/v${new_version}...HEAD|" \
    -e "/^\[Unreleased\]/a [${new_version}] https://github.com/kannibalox/pyrosimple/compare/v${prev_version}...v${new_version}" \
    CHANGELOG.md
awk "/## \\[${new_version}\\]/,/## \\[${prev_version}\\]/" CHANGELOG.md | sed -e 1,2d | head -n -2 > RELEASE_NOTE.md
poetry build
