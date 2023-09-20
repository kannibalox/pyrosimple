""" Perform raw XMLRPC calls.

    Copyright (c) 2010 The PyroScope Project <pyroscope.project@gmail.com>
"""


import difflib
import json
import logging
import os
import shlex
import sys
import tempfile
import textwrap

from pprint import pformat
from xmlrpc import client as xmlrpc_client

from pyrosimple import config, error
from pyrosimple.scripts.base import ScriptBaseWithConfig
from pyrosimple.util import fmt, rpc


def read_blob(arg: str) -> bytes:
    """Read a BLOB from given ``@arg``."""
    if arg == "@-":
        return sys.stdin.buffer.read()

    if any(arg.startswith(f"@{x}://") for x in ["http", "https", "ftp", "file"]):
        try:
            import requests  # pylint: disable=import-outside-toplevel

            response = requests.get(arg[1:], timeout=60)
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            raise error.UserError(str(exc))

    with open(os.path.expanduser(arg[1:]), "rb") as handle:
        return handle.read()


class RtorrentXmlRpc(ScriptBaseWithConfig):
    """
    Perform raw rTorrent RPC calls, like "rtxmlrpc throttle.global_up.max_rate".

    Start arguments with "+" or "-" to indicate they're numbers (type i4 or i8).
    Use "[1,2,..." for arrays. Use "@" to indicate binary data, which can be
    followed by a file path (e.g. "@/path/to/file"), a URL (https, http, ftp,
    and file are supported), or '-' to read from stdin.
    """

    def __init__(self):
        super().__init__()
        self.proxies = []

    def add_options(self):
        """Add program options."""
        super().add_options()

        # basic options
        self.parser.add_argument("method", nargs="?", help="method name")
        self.parser.add_argument("args", nargs="*", help="arguments to method")
        self.parser.add_argument(
            "-o",
            "--output-format",
            default="pretty",
            choices=["pretty", "repr", "json"],
            help="Output format to use. Defaults to 'pretty'",
        )
        self.add_bool_option(
            "-i",
            "--as-import",
            help="execute each argument as a private command using 'import'",
        )
        self.add_bool_option(
            "--session",
            "--restore",
            help="restore session state from .rtorrent session file(s)",
        )
        self.add_bool_option(
            "--repl",
            help="Open an interactive prompt to run commands",
        )

    def open(self):
        """Open connections and return proxies."""
        if not self.proxies:
            if not config.settings["SCGI_URL"]:
                config.autoload_scgi_url()
            if not config.settings["SCGI_URL"]:
                self.log.error(
                    "Unable to automatically detect a RPC connection, see"
                    " https://kannibalox.github.io/pyrosimple/configuration/#reference"
                )
            for url in config.multi_connection_lookup(
                self.options.url or config.settings["SCGI_URL"]
            ):
                if url:
                    self.proxies.append(rpc.RTorrentProxy(url))
        return self.proxies

    def cooked(self, raw_args):
        """Return interpreted / typed list of args."""
        args = []
        for arg in raw_args:
            if arg and arg[0] in "+-":
                try:
                    arg = int(arg, 10)
                except (ValueError, TypeError) as exc:
                    self.log.warning("Not a valid number: %r (%s)", arg, exc)
            elif arg.startswith("[["):  # escaping, not a list
                arg = arg[1:]
            elif arg == "[]":
                arg = []
            elif arg.startswith("["):
                arg = arg[1:].split(",")
                if all(i.isdigit() for i in arg):
                    arg = [int(i, 10) for i in arg]
            elif arg.startswith("@"):
                arg = xmlrpc_client.Binary(read_blob(arg))
            args.append(arg)

        return args

    def execute(self, proxy, method, args):
        """Execute given RPC call."""
        try:
            result = getattr(proxy, method)(*tuple(args))
        except rpc.ERRORS as exc:
            self.log.error(
                "While calling %s(%s) via %s: %s",
                method,
                ", ".join(repr(i) for i in args),
                proxy,
                exc,
            )
            if f"Method '{method}' not defined" in str(
                exc
            ) or f"method not found: {method}" in str(exc):
                cmds = difflib.get_close_matches(
                    method, proxy.system.listMethods() + ["system.listMethods"]
                )
                if cmds:
                    print("The most similar methods are:")
                    for w in cmds:
                        print("-", w)
                else:
                    print(
                        "No similar methods found, try `rtxmlrpc system.listMethods` to see a full list of available methods."
                    )
            if isinstance(exc, rpc.HashNotFound):
                self.return_code = error.EX_NOINPUT
            else:
                self.return_code = error.EX_DATAERR
        else:
            if self.log.isEnabledFor(
                logging.WARNING
            ):  # Hack to hide output when `-q` is in effect
                if self.options.output_format == "repr":
                    result = pformat(result)
                elif self.options.output_format == "json":
                    result = json.dumps(result)
                else:
                    result = fmt.rpc_result_to_string(result)
                print(result)

    def do_import(self):
        """Handle import files or streams passed with '-i'."""
        tmp_import = None
        # Concatenate arguments
        self.args = [self.options.method] + self.args
        try:
            if self.args[0].startswith("@") and self.args[0] != "@-":
                import_file = os.path.expanduser(self.args[0][1:])
                if not os.path.isfile(import_file):
                    self.parser.error(f"File not found (or not a file): {import_file}")
                args = (rpc.NOHASH, os.path.abspath(import_file))
            else:
                script_text = "\n".join(self.args + [""])
                if script_text == "@-\n":
                    script_text = sys.stdin.read()

                with tempfile.NamedTemporaryFile(
                    suffix=".rc", prefix="rtxmlrpc-", delete=False
                ) as handle:
                    handle.write(script_text.encode("utf-8"))
                    tmp_import = handle.name
                args = (rpc.NOHASH, tmp_import)

            for proxy in self.open():
                self.execute(proxy, "import", args)
        finally:
            if tmp_import and os.path.exists(tmp_import):
                os.remove(tmp_import)

    def do_command(self):
        """Call a single command with arguments."""
        if not self.options.method:
            self.parser.print_help()
            print(
                "No method name given! Try `rtxmlrpc system.listMethods` to see a list of available methods."
            )
            sys.exit(error.EX_USAGE)
        method = self.options.method

        raw_args = self.args
        if "=" in method:
            if raw_args:
                self.parser.error(
                    "Please don't mix rTorrent and shell argument styles!"
                )
            method, raw_args = method.split("=", 1)
            raw_args = raw_args.split(",")

        for proxy in self.open():
            self.execute(proxy, method, self.cooked(raw_args))

    def print_repl_help(self):
        """Short REPL help output"""
        print(
            textwrap.dedent(
                r"""\
        Entering prompt. Press Ctrl-D to exit.
        rTorrent XMLRPC REPL Help Summary
        =================================

        <Ctrl-d>            Exit the REPL.
        <Ctrl-c>            Cancel the current command.
        ?                   Show this help text.
        \help               Show this help text.
        \stats              Show current call stats.
        \connect URL        Connect to a different host
        cmd=arg1,arg2,..    Call a XMLRPC command"""
            )
        )

    def do_repl(self):
        """Run a simple REPL loop"""
        self.open()
        # pylint: disable=import-outside-toplevel
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import WordCompleter

        # pylint: enable=import-outside-toplevel

        session = PromptSession(
            completer=WordCompleter(
                self.proxies[0].system.listMethods()
                + [r"\help", r"\stats", r"\connect"],
                WORD=True,
            )
        )
        self.print_repl_help()
        while True:
            try:
                label = ",".join([p.system.hostname() for p in self.proxies])
                text = session.prompt(f"{label}> ")
                if not text:
                    continue
                if text in {"?", r"\help"}:
                    self.print_repl_help()
                    continue
                if text == r"\stats":
                    print(self.rpc_stats())
                    continue
                if text.startswith(r"\connect "):
                    config.settings["SCGI_URL"] = text.split(" ")[1]
                    self.proxies = []
                    self.open()
                    continue
                self.options.method, *self.args = shlex.split(text)
                self.do_command()
            except KeyboardInterrupt:
                continue  # Control-C pressed. Try again.
            except EOFError:
                break  # Control-D pressed.

    def mainloop(self):
        """The main loop."""
        # Dispatch to handlers
        if self.options.as_import:
            self.do_import()
        elif self.options.repl:
            self.do_repl()
        else:
            self.do_command()

        # RPC stats
        self.log.debug("RPC stats: %s", self.rpc_stats())


def run():  # pragma: no cover
    """The entry point."""
    RtorrentXmlRpc().run()


if __name__ == "__main__":
    run()
