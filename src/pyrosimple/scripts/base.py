""" Command Line Script Support.

    Copyright (c) 2009, 2010 The PyroScope Project <pyroscope.project@gmail.com>
"""


import errno
import logging.config
import os
import signal
import sys
import textwrap
import time
import traceback

from argparse import ArgumentParser, Namespace, RawDescriptionHelpFormatter
from typing import List, Optional

import shtab

from pyrosimple import error
from pyrosimple.util import pymagic


class ScriptBase:
    """Base class for command line interfaces."""

    # additonal stuff appended after the command handler's docstring
    ADDITIONAL_HELP: List[str] = []

    def __init__(self) -> None:
        """Initialize CLI."""
        self.startup = time.time()
        # self.LOG exists only for backwards compatibility
        self.LOG = self.log = pymagic.get_class_logger(self)

        self.args: Optional[List] = None
        self.options = Namespace()
        self.return_code = 0
        self.engine = None
        self.intermixed_args = False

        logging.basicConfig(level=logging.WARNING)
        # For python 3.7 compatibility
        try:
            import importlib.metadata  # pylint: disable=import-outside-toplevel

            version = importlib.metadata.version(  # pylint: disable=no-member
                "pyrosimple"
            )
        except ImportError:
            import importlib_metadata  # pylint: disable=import-outside-toplevel

            version = importlib_metadata.version(  # pylint: disable=no-member
                "pyrosimple"
            )
        implementation = sys.implementation.name
        if implementation == "cpython":
            implementation = "Python"
        version_info = f"{version} on {implementation} {sys.version.split()[0]}"

        self.parser = ArgumentParser(
            formatter_class=RawDescriptionHelpFormatter,
            description="%(prog)s "
            + version_info
            + "\n\n"
            + textwrap.dedent((self.__doc__ or "").rstrip()).lstrip("\n")
            + "\n".join(self.ADDITIONAL_HELP)
            + "\n\nFor more details, see the full documentation at"
            + "\n    https://kannibalox.github.io/pyrosimple/",
        )
        shtab.add_argument_to(self.parser, ["--print-completion"])

        self.parser.add_argument(
            "--version", action="version", version=f"%(prog)s {version_info}"
        )

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
            kwargs["help"] += f" [{kwargs['default']}]"
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
            default=logging.WARNING,
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

        if self.intermixed_args:
            self.options = self.parser.parse_intermixed_args(self.args)
        else:
            self.options = self.parser.parse_args(self.args)
        self.args = getattr(self.options, "args", None)

        if self.options.log_level:
            logging.getLogger("pyrosimple").setLevel(self.options.log_level)

        self.log.debug(
            "Options: %s",
            ", ".join("%s=%r" % i for i in sorted(vars(self.options).items())),
        )

    def fatal(self, msg, exc=None):
        """Exit on a fatal error."""
        if exc is not None:
            self.log.fatal("%s (%s)", msg, exc)
            if logging.getLogger().isEnabledFor(logging.DEBUG):
                return  # let the caller re-raise it
        else:
            self.log.fatal(msg)
        sys.exit(error.EX_SOFTWARE)

    def run(self, args: Optional[List[str]] = None):
        """The main program skeleton."""
        if args is not None:
            self.args = args
        try:
            try:
                # Preparation steps
                self.get_options()

                # Template method with the tool's main loop
                self.mainloop()
            except error.LoggableError:
                print(traceback.format_exc())
                sys.exit(error.EX_SOFTWARE)
            except KeyboardInterrupt:
                print()
                self.log.critical("Aborted by CTRL-C!\n")
                signal.signal(signal.SIGINT, signal.SIG_DFL)
                os.kill(os.getpid(), signal.SIGINT)
            except OSError as exc:
                # [Errno 32] Broken pipe?
                if exc.errno == errno.EPIPE:
                    print(f"\n{exc}, exiting!\n", file=sys.stderr)
                    sys.exit(error.EX_IOERR)
                else:
                    raise
        finally:
            # Shut down
            if self.options:  ## No time logging on --version and such
                running_time = time.time() - self.startup
                self.log.info("Total time: %.3f seconds.", running_time)
            logging.shutdown()

        # Special exit code?
        if self.return_code:
            sys.exit(self.return_code)

    def add_options(self):
        """Add program options."""

    def mainloop(self):
        """The main loop."""
        raise NotImplementedError()

    def rpc_stats(self) -> str:
        """Return a string with RPC statistics"""

        from pyrosimple import io  # pylint: disable=import-outside-toplevel
        from pyrosimple.util import fmt  # pylint: disable=import-outside-toplevel

        req_num = int(io.scgi.request_counter._value.get())
        req_sz = fmt.human_size(io.scgi.request_size_counter._value.get())
        req_time = round(
            list(io.scgi.response_time_summary._child_samples())[1].value, 3
        )
        resp_sz = fmt.human_size(io.scgi.response_size_counter._value.get())
        return f"{req_num} requests ({req_sz}) in {req_time}s (response {resp_sz})"


class ScriptBaseWithConfig(ScriptBase):  # pylint: disable=abstract-method
    """CLI tool with configuration support."""

    def add_options(self):
        super().add_options()
        self.parser.add_argument("-U", "--url", help="URL to rtorrent instance")

    def get_options(self):
        """Get program options."""
        super().get_options()
        # pylint: disable=import-outside-toplevel
        from pyrosimple import config

        # pylint: enable=import-outside-toplevel

        if self.options.url:
            config.settings["SCGI_URL"] = config.lookup_connection_alias(
                self.options.url
            )
        config.load_custom_py()
