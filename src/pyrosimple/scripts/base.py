# -*- coding: utf-8 -*-
""" Command Line Script Support.

    Copyright (c) 2009, 2010 The PyroScope Project <pyroscope.project@gmail.com>
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


import errno
import logging.config
import os
import sys
import textwrap
import time
import traceback

from argparse import ArgumentParser
from typing import List

from pyrosimple import config, error
from pyrosimple.util import load_config, pymagic


class ScriptBase:
    """Base class for command line interfaces."""

    # log level for user-visible standard logging
    STD_LOG_LEVEL = logging.INFO

    # argument description for the usage information
    ARGS_HELP = "<log-base>..."

    # additonal stuff appended after the command handler's docstring
    ADDITIONAL_HELP: List[str] = []

    # Can be empty or None in derived classes
    COPYRIGHT = "Copyright (c) 2009 - 2018 Pyroscope Project"

    # Can be made explicit in derived classes (for external tools)
    VERSION = None

    @classmethod
    def setup(cls, _=None):
        """Set up the runtime environment."""
        logging.basicConfig(level=logging.WARNING)

    def __init__(self):
        """Initialize CLI."""
        self.startup = time.time()
        self.LOG = pymagic.get_class_logger(self)
        self.config_dir = ""

        self.args = None
        self.options = None
        self.return_code = 0

        try:
            import importlib.metadata  # pylint: disable=import-outside-toplevel

            self.__version__ = importlib.metadata.version("pyrosimple")
        except ImportError:
            self.__version__ = "unknown"
        self.version_info = "{} on Python {}".format(
            self.__version__, sys.version.split()[0]
        )

        self.parser = ArgumentParser(
            usage="%(prog)s [options] " + self.ARGS_HELP + "\n\n"
            "%(prog)s "
            + self.version_info
            + ("\n" + self.COPYRIGHT if self.COPYRIGHT else "")
            + "\n\n"
            + textwrap.dedent(self.__doc__.rstrip()).lstrip("\n")
            + "\n".join(self.ADDITIONAL_HELP)
            + "\n\nFor more details, see the full documentation at"
            + "\n\n    https://pyrosimple.readthedocs.io/",
        )

        self.parser.add_argument(
            "--version", action="version", version="%(prog)s " + self.version_info
        )
        self.parser.add_argument("args", nargs="*")

    def add_bool_option(self, *args, **kwargs):
        """Add a boolean option.

        @keyword help: Option description.
        """
        dest = (
            [o for o in args if o.startswith("--")][0]
            .replace("--", "")
            .replace("-", "_")
        )
        self.parser.add_argument(
            dest=dest, action="store_true", default=False, help=kwargs["help"], *args
        )

    def add_value_option(self, *args, **kwargs):
        """Add a value option.

        @keyword dest: Destination attribute, derived from long option name if not given.
        @keyword action: How to handle the option.
        @keyword help: Option description.
        @keyword default: If given, add this value to the help string.
        """
        kwargs["metavar"] = args[-1]
        if "dest" not in kwargs:
            kwargs["dest"] = (
                [o for o in args if o.startswith("--")][0]
                .replace("--", "")
                .replace("-", "_")
            )
        if "default" in kwargs and kwargs["default"]:
            kwargs["help"] += " [%s]" % kwargs["default"]
        if "choices" in kwargs:
            del kwargs["type"]
        self.parser.add_argument(*args[:-1], **kwargs)

    def get_options(self):
        """Get program options."""
        self.parser.add_argument(
            "-q",
            "--quiet",
            "--cron",  # For backwards compatibility
            help="silence warnings",
            dest="log_level",
            action="store_const",
            const=logging.CRITICAL,
        )
        self.parser.add_argument(
            "--debug",
            help="show detailed messages",
            dest="log_level",
            action="store_const",
            const=logging.DEBUG,
        )
        self.parser.add_argument(
            "-v",
            "--verbose",
            help="show additional information",
            dest="log_level",
            action="store_const",
            const=logging.INFO,
        )

        # Template method to add options of derived class
        self.add_options()

        self.options = self.parser.parse_args()
        self.args = self.options.args

        if self.options.log_level:
            logging.getLogger().setLevel(self.options.log_level)

        self.LOG.debug(
            "Options: %s",
            ", ".join("%s=%r" % i for i in sorted(vars(self.options).items())),
        )

    def fatal(self, msg, exc=None):
        """Exit on a fatal error."""
        if exc is not None:
            self.LOG.fatal("%s (%s)", msg, exc)
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                return  # let the caller re-raise it
        else:
            self.LOG.fatal(msg)
        sys.exit(error.EX_SOFTWARE)

    def run(self):
        """The main program skeleton."""
        log_total = True

        try:
            try:
                # Preparation steps
                self.get_options()

                # Template method with the tool's main loop
                self.mainloop()
            except error.LoggableError as exc:
                traceback.print_exception(exc)
                sys.exit(error.EX_SOFTWARE)
            except KeyboardInterrupt:
                self.LOG.critical("\n\nAborted by CTRL-C!\n", file=sys.stderr)
                sys.exit(error.EX_TEMPFAIL)
            except IOError as exc:
                # [Errno 32] Broken pipe?
                if exc.errno == errno.EPIPE:
                    print("\n%s, exiting!\n" % exc, file=sys.stderr)
                    sys.exit(error.EX_IOERR)
                else:
                    raise
        finally:
            # Shut down
            if log_total and self.options:  ## No time logging on --version and such
                running_time = time.time() - self.startup
                self.LOG.log(
                    self.STD_LOG_LEVEL, "Total time: %.3f seconds.", running_time
                )
            logging.shutdown()

        # Special exit code?
        if self.return_code:
            sys.exit(self.return_code)

    def add_options(self):
        """Add program options."""

    def mainloop(self):
        """The main loop."""
        raise NotImplementedError()


class ScriptBaseWithConfig(ScriptBase):  # pylint: disable=abstract-method
    """CLI tool with configuration support."""

    CONFIG_DIR_DEFAULT = "~/.pyroscope"
    OPTIONAL_CFG_FILES: List[str] = []

    def add_options(self):
        """Add configuration options."""
        super().add_options()

        self.add_value_option(
            "--config-dir",
            "DIR",
            help="configuration directory [{}]".format(
                os.environ.get("PYRO_CONFIG_DIR", self.CONFIG_DIR_DEFAULT)
            ),
        )
        self.add_value_option(
            "--config-file",
            "PATH",
            action="append",
            default=[],
            help="additional config file(s) to read",
        )
        self.add_value_option(
            "-D",
            "--define",
            "KEY=VAL",
            default=[],
            action="append",
            dest="defines",
            help="override configuration attributes",
        )

    def get_options(self):
        """Get program options."""
        super().get_options()

        self.config_dir = os.path.abspath(
            os.path.expanduser(
                self.options.config_dir
                or os.environ.get("PYRO_CONFIG_DIR", None)
                or self.CONFIG_DIR_DEFAULT
            )
        )
        load_config.ConfigLoader(self.config_dir).load(
            self.OPTIONAL_CFG_FILES + self.options.config_file
        )
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            config.debug = True

        for key_val in self.options.defines:
            try:
                key, val = key_val.split("=", 1)
            except ValueError as exc:
                raise error.UserError("Bad config override %r (%s)" % (key_val, exc))
            else:
                setattr(config, key, load_config.validate(val))

class PromptDecorator:
    """Decorator for interactive commands."""

    def __init__(self, script_obj):
        """Initialize with containing tool object."""
        self.script = script_obj

    def add_options(self):
        """Add program options, must be called in script's addOptions()."""
        # These options need to be conflict-free to the containing
        # script, i.e. avoid short options if possible.
        self.script.add_bool_option(
            "-i",
            "--interactive",
            help="interactive mode (prompt before changing things)",
        )
        self.script.add_bool_option(
            "--yes", help="positively answer all prompts (e.g. --delete --yes)"
        )

    def ask_bool(self, question, default=True):
        """Ask the user for Y)es / N)o / Q)uit.

        If "Q" is entered, this method will exit with RC=3.
        Else, the user's choice is returned.

        Note that the options --non-interactive and --defaults
        also influence the outcome.
        """
        if self.script.options.yes:
            return True
        elif self.script.options.dry_run or not self.script.options.interactive:
            return default
        else:
            # Let the user decide
            choice = "*"
            while choice not in "YNAQ":
                choice = input(
                    "%s? [%s)es, %s)o, a)ll yes, q)uit]: "
                    % (
                        question,
                        "yY"[int(default)],
                        "Nn"[int(default)],
                    )
                )
                choice = choice[:1].upper() or "NY"[int(default)]

            if choice == "Q":
                self.quit()
            if choice == "A":
                self.script.options.yes = True
                choice = "Y"

            return choice == "Y"

    def quit(self):
        """Exit the program due to user's choices."""
        self.script.LOG.warn("Abort due to user choice!")
        sys.exit(error.EX_TEMPFAIL)
