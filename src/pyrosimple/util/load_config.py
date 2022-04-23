# -*- coding: utf-8 -*-
""" Configuration Loader.

    For details, see https://pyrosimple.readthedocs.io/en/latest/setup.html

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import configparser as ConfigParser
import errno
import importlib
import importlib.resources
import io
import os
import re

from pathlib import Path


try:
    resources_files = importlib.resources.files
except AttributeError:
    # pylint: disable=import-error
    import importlib_resources

    resources_files = importlib_resources.files

from pyrosimple import config, error
from pyrosimple.util import pymagic


class ConfigLoader:
    """Populates this module's dictionary with the user-defined configuration values."""

    CONFIG_INI = "config.ini"
    INTERPOLATION_ESCAPE = re.compile(r"(?<!%)%[^%(]")

    def __init__(self, config_dir=None):
        """Create loader instance."""
        self.config_dir = config_dir or os.path.join(
            os.path.expanduser("~"), ".pyroscope"
        )
        self.LOG = pymagic.get_class_logger(self)
        self._loaded = False

    def _update_config(self, namespace):  # pylint: disable=no-self-use
        """Inject the items from the given dict into the configuration."""
        for key, val in namespace.items():
            setattr(config, key, val)

    def _interpolation_escape(self, namespace):
        """Re-escape interpolation strings."""
        for key, val in namespace.items():
            if "%" in val:
                namespace[key] = self.INTERPOLATION_ESCAPE.sub(
                    lambda match: "%" + match.group(0), val
                )

    def _validate_namespace(self, namespace):
        """Validate the given namespace. This method is idempotent!"""
        # Update config values (so other code can access them in the bootstrap phase)
        self._update_config(namespace)

        # Re-escape output formats
        self._interpolation_escape(namespace["formats"])

        # Create engine from module specs
        namespace["config_validator_callbacks"] = pymagic.import_name(
            config.settings.CONFIG_VALIDATOR_CALLBACKS
        )

        # Do some standard type conversions
        for key in namespace:
            # Split lists
            if key.endswith("_list") and isinstance(namespace[key], str):
                namespace[key] = [
                    i.strip() for i in namespace[key].replace(",", " ").split()
                ]

            # Resolve factory and callback handler lists
            elif any(
                key.endswith(i) for i in ("_factories", "_callbacks")
            ) and isinstance(namespace[key], str):
                namespace[key] = [
                    pymagic.import_name(i.strip())
                    for i in namespace[key].replace(",", " ").split()
                ]

        # Update config values again
        self._update_config(namespace)

    def _set_from_ini(self, namespace, ini_file):
        """Copy values from loaded INI file to namespace."""
        # Isolate global values
        global_vars = dict(
            (key, val) for key, val in namespace.items() if isinstance(val, str)
        )

        # Copy all sections
        for section in ini_file.sections():
            # Get values set so far
            if section == "GLOBAL":
                raw_vars = global_vars
            else:
                raw_vars = namespace.setdefault(section.lower(), {})

            # Override with values set in this INI file
            raw_vars.update(dict(ini_file.items(section, raw=True)))

            # Interpolate and validate all values
            if section == "FORMATS":
                self._interpolation_escape(raw_vars)
            raw_vars.update(
                dict((key, val) for key, val in ini_file.items(section, vars=raw_vars))
            )

        # Update global values
        namespace.update(global_vars)

    def _set_defaults(self, namespace, optional_cfg_files):
        """Set default values in the given dict."""
        # Add current configuration directory
        namespace["config_dir"] = self.config_dir

        # Load defaults
        for idx, cfg_file in enumerate([self.CONFIG_INI] + optional_cfg_files):
            if any(i in cfg_file for i in set("/" + os.sep)):
                continue  # skip any non-plain filenames

            try:
                with resources_files("pyrosimple").joinpath(
                    "data/config/", cfg_file
                ).open("rb") as handle:
                    defaults = handle.read()
            except IOError as exc:
                if idx and exc.errno == errno.ENOENT:
                    continue
                raise

            ini_file = ConfigParser.SafeConfigParser()
            ini_file.optionxform = str  # case-sensitive option names
            ini_file.read_file(io.StringIO(defaults.decode("utf-8")), "<defaults>")
            self._set_from_ini(namespace, ini_file)

    def _load_ini(self, namespace, config_file):
        """Load INI style configuration."""
        self.LOG.debug("Loading %r...", config_file)
        ini_file = ConfigParser.SafeConfigParser()
        ini_file.optionxform = str  # case-sensitive option names
        if ini_file.read(config_file):
            self._set_from_ini(namespace, ini_file)
        else:
            self.LOG.warning(
                "Configuration file %r not found,"
                " use the command 'pyroadmin --create-config' to create it!",
                config_file,
            )

    def _load_py(self, namespace, config_file):
        """Load scripted configuration."""
        if config_file and os.path.isfile(config_file):
            self.LOG.debug("Loading %r...", config_file)
            with open(config_file, "rb") as handle:
                # pylint: disable=exec-used
                exec(
                    compile(handle.read(), config_file, "exec"),
                    vars(config),
                    namespace,
                )
        else:
            self.LOG.warning("Configuration file %r not found!", config_file)

    def load(self, optional_cfg_files=None):
        """Actually load the configuation from either
        the default location or the given directory."""
        optional_cfg_files = optional_cfg_files or []

        # Guard against coding errors
        if self._loaded:
            raise RuntimeError("INTERNAL ERROR: Attempt to load configuration twice!")

        try:
            # Load configuration
            namespace = {}
            self._set_defaults(namespace, optional_cfg_files)

            self._load_ini(namespace, os.path.join(self.config_dir, self.CONFIG_INI))

            for cfg_file in optional_cfg_files:
                if not os.path.isabs(cfg_file):
                    cfg_file = os.path.join(self.config_dir, cfg_file)

                if os.path.exists(cfg_file):
                    self._load_ini(namespace, cfg_file)

            self._validate_namespace(namespace)
            pyconfig = Path(config.settings.get("CONFIG_PY")).expanduser()
            if pyconfig.exists():
                self._load_py(namespace, pyconfig)
            self._validate_namespace(namespace)

            pymagic.import_name(config.settings.CONFIG_VALIDATOR_CALLBACKS)()
        except ConfigParser.ParsingError as exc:
            raise error.UserError(exc)

        # Ready to go...
        self._loaded = True
