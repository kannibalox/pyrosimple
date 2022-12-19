""" rTorrent Control.

    Copyright (c) 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""

import argparse
import functools
import json
import logging
import re
import shlex
import subprocess
import sys
import time

from multiprocessing.pool import ThreadPool
from typing import Callable, List, Union

from pyrosimple import error
from pyrosimple.scripts.base import ScriptBaseWithConfig
from pyrosimple.util import fmt, pymagic, rpc
from pyrosimple.util.parts import DefaultBunch


def print_help_fields():
    """Print help about fields and field formatters."""
    from pyrosimple.torrent import engine  # pylint: disable=import-outside-toplevel

    # Mock entries, so they fulfill the expectations towards a field definition
    def custom_manifold():
        "named rTorrent custom attribute, e.g. 'custom_completion_target'"
        return ("custom_KEY", custom_manifold)

    def kind_manifold():
        "file types that contribute at least N% to the item's total size"
        return ("kind_N", kind_manifold)

    print("")
    print("Fields are:")
    print(
        "\n".join(
            [
                "  %-21s %s" % (name, field.__doc__)
                for name, field in sorted(
                    list(engine.FIELD_REGISTRY.items())
                    + [
                        custom_manifold(),
                        kind_manifold(),
                    ]
                )
            ]
        )
    )


def print_help_filters():
    """Print help about template filters."""
    print("")
    print("In addition to the filters below, jinja2 has some filters built-in:")
    print(
        "  https://jinja.palletsprojects.com/en/3.1.x/templates/#list-of-builtin-filters"
    )
    print("pyrosimple-specific filters:")
    for name, method in fmt.__dict__.items():
        if name.startswith("fmt_"):
            print("  %-21s %s" % (name[4:], method.__doc__))


class FieldStatistics:
    """Collect statistical values for the fields of a search result."""

    def __init__(self):
        "Initialize accumulator"
        self.size = 0
        self.errors = DefaultBunch(int)
        self.total = DefaultBunch(int)
        self.min = DefaultBunch(int)
        self.max = DefaultBunch(int)
        self._basetime = time.time()
        self.intermixed_args = True

    def __bool__(self):
        "Truth"
        return bool(self.total)

    def __nonzero__(self):
        return self.__bool__()

    def add(self, field, val):
        "Add a sample"
        # pylint: disable=import-outside-toplevel
        from pyrosimple.torrent import engine
        from pyrosimple.util import matching

        # pylint: enable=import-outside-toplevel

        if engine.FIELD_REGISTRY[field]._matcher is matching.TimeFilter:
            val = self._basetime - val

        try:
            self.total[field] += val
            self.min[field] = min(self.min[field], val) if field in self.min else val
            self.max[field] = max(self.max[field], val)
            self.size += 1
        except (ValueError, TypeError):
            self.errors[field] += 1

    @property
    def average(self):
        "Calculate average"
        result = DefaultBunch(str)

        # Calculate average if possible
        if self.size:
            result.update(
                (key, "" if isinstance(val, str) else val / self.size)
                for key, val in list(self.total.items())
            )

        # Handle time fields
        # for key, fielddef in  engine.FIELD_REGISTRY.items():
        #    if key in result and fielddef._matcher is matching.TimeFilter:
        #       result[key] = ''
        # for key, fielddef in  engine.FIELD_REGISTRY.items():
        #    if key in result and fielddef._matcher is matching.TimeFilter:
        #        result[key] = engine._fmt_duration(result[key])
        # print self.total
        # print result
        return result


class RtorrentAction(argparse.Action):
    """This class is used by the argparse action parameter for adding rtcontrol actions to a master list in the namespace.

    There is a rather unfortunate name collision between argparse's actions and rtcontrol's actions.
    'const' is used as the method name to call, with the arguments being pulled from the value"""

    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        """Build the action, default to 1 narg since that's the most common"""
        if nargs is None:
            nargs = 1
        if "const" not in kwargs:
            kwargs["const"] = option_strings[0].lstrip("-").replace("-", "_")
        self.interactive = False
        super().__init__(option_strings, dest, nargs, **kwargs)

    def __call__(
        self, parser, namespace, values, option_string=None, interactive=False
    ):
        """Add any action to the namespace in order"""
        actions = getattr(namespace, "actions", [])
        actions.append(
            {"method": self.const, "args": values, "interactive": interactive}
        )
        namespace.actions = actions


class RtorrentInteractiveAction(RtorrentAction):
    """Simple class to mark commands as interactive"""

    def __call__(self, *args, **kwargs):
        """Call the parent, but with interactive=True"""
        super().__call__(*args, **kwargs, interactive=True)


class RtorrentControl(ScriptBaseWithConfig):
    """
    Control and inspect rTorrent from the command line.

    Filter expressions take the form "<field>=<value>", and all expressions must
    be met (AND). If a field name is omitted, "name" is assumed. You can also use
    uppercase OR to build a list of alternative conditions.

    For numeric fields, a leading "+" means greater than, a leading "-" means less
    than. For string fields, the value is a glob pattern (*, ?, [a-z], [!a-z]), or
    a regex match enclosed by slashes. All string comparisons are case-ignoring.
    Multiple values separated by a comma indicate several possible choices (OR).
    "!" in front of a filter value negates it (NOT).

    See https://kannibalox.github.io/pyrosimple/usage-rtcontrol/#examples for more.

    Examples:
      - All 1:1 seeds         ratio=+1
      - All active torrents   xfer=+0
      - All seeding torrents  up=+0
      - Slow torrents         down=+0 down=-5k
      - Older than 2 weeks    completed=+2w
      - Big stuff             size=+4g
      - 1:1 seeds not on NAS  ratio=+1 'realpath=!/mnt/*'
      - Music                 kind=flac,mp3
    """

    # argument description for the usage information
    ARGS_HELP = "<filter>..."

    # additional stuff appended after the command handler's docstring
    ADDITIONAL_HELP = [
        "",
        "",
        "Use --help to get a list of all options.",
        "Use --help-fields to list all fields and their description.",
    ]

    # additional values for output formatting
    FORMATTER_DEFAULTS = dict(
        now=time.time,
    )

    # choices for --ignore
    IGNORE_OPTIONS = ("0", "1")

    # choices for --prio
    PRIO_OPTIONS = ("0", "1", "2", "3")

    # choices for --alter
    ALTER_MODES = ("append", "remove")

    # action options that perform some change on selected items
    ACTION_MODES = (
        # TODO: --pause, --resume?
        # TODO: implement --clean-partial
        # self.add_bool_option("--clean-partial",
        #    help="remove partially downloaded 'off'ed files (also stops downloads)")
        # TODO: --move / --link output_format / the formatted result is the target path
        #           if the target contains a '//' in place of a '/', directories
        #           after that are auto-created
        #           "--move tracker_dated", with a custom output format
        #           like "tracker_dated = ~/done//$(alias)s/$(completed).7s",
        #           will move to ~/done/OBT/2010-08 for example
        #        self.add_value_option("--move", "TARGET",
        #            help="move data to given target directory (implies -i, can be combined with --delete)")
        # TODO: --copy, and --move/--link across devices
    )

    def add_options(self):
        """Add program options."""
        super().add_options()

        # basic options
        self.add_bool_option(
            "--help-fields", help="show available fields and their description"
        )
        self.add_bool_option(
            "-n", "--dry-run", help="don't commit changes, just tell what would happen"
        )

        # output control
        output_group = self.parser.add_argument_group("output")
        output_group.add_argument(
            "-S",
            "--shell",
            help="escape output following shell rules",
            action="store_true",
        )
        output_group.add_argument(
            "-0",
            "--nul",
            "--print0",
            action="store_true",
            help="use a NUL character instead of a linebreak after items",
        )
        output_group.add_argument(
            "-+",
            "--stats",
            help="add sum / avg / median of numerical fields",
            action="store_true",
        )
        output_group.add_argument(
            "--summary",
            help="print only statistical summary, without the items",
            action="store_true",
        )
        output_group.add_argument(
            "--json",
            help="dump default fields of all items as JSON (use '-o f1,f2,...' to specify fields)",
            action="store_true",
        )
        output_group.add_argument(
            "-o",
            "--output-format",
            metavar="FORMAT",
            help="specify display format (use '-o-' to disable item display)",
        )
        output_group.add_argument(
            "-O",
            "--output-template",
            metavar="FILE",
            help="pass control of output formatting to the specified template",
        )
        output_group.add_argument(
            "-s",
            "--sort-fields",
            metavar="FIELD",
            help="fields used for sorting, descending if prefixed with a '-'; '-s*' uses output field list",
        )
        output_group.add_argument(
            "-r",
            "--reverse-sort",
            help="reverse the sort order",
            action="store_true",
        )
        self.add_value_option(
            "-/",
            "--select",
            "[N-]M",
            help="select result subset by item position (counting from 1)",
        )
        self.add_bool_option(
            "-V", "--view-only", help="show search result only in default ncurses view"
        )
        self.add_value_option(
            "--to-view",
            "--to",
            "NAME",
            help="show search result only in named ncurses view",
        )
        self.add_bool_option(
            "--detach",
            help="run command in background",
        )
        self.add_bool_option(
            "-i",
            "--interactive",
            help="interactive mode (prompt before changing things)",
        )
        self.add_bool_option(
            "--yes", help="positively answer all prompts (e.g. --delete --yes)"
        )
        self.add_value_option(
            "--alter-view",
            "--alter",
            "MODE",
            type="choice",
            default=None,
            choices=self.ALTER_MODES,
            help="alter view according to mode: {} (modifies -V and --to behaviour)".format(
                ", ".join(self.ALTER_MODES)
            ),
        )
        self.add_bool_option(
            "--tee-view",
            "--tee",
            help="ADDITIONALLY show search results in ncurses view (modifies -V and --to behaviour)",
        )
        self.add_value_option(
            "--from-view",
            "--from",
            "NAME",
            help="select only items that are on view NAME (NAME can be an info hash to quickly select a single item)",
        )
        self.add_value_option(
            "-M",
            "--modify-view",
            "NAME",
            help="get items from given view and write result back to it (short-cut to combine --from-view and --to-view)",
        )
        self.parser.add_argument(
            "-Q",
            "--fast-query",
            choices=("=", "0", "1", "2"),
            default="=",
            metavar="LEVEL",
            help="enable query optimization (=: use config; 0: off; 1: safe; 2: danger seeker)",
        )
        action_group = self.parser.add_argument_group(
            "actions", "Can be set more than once, and order matters."
        )
        action_group.add_argument(
            "--call",
            action=RtorrentInteractiveAction,
            help="call an OS command pattern in the shell (implies -i)",
            metavar="CMD",
        )
        action_group.add_argument(
            "--move-to-host",
            action=RtorrentInteractiveAction,
            help="move item to another host (implies -i)",
            metavar="URL",
        )
        action_group.add_argument(
            "--move",
            action=RtorrentInteractiveAction,
            help="move item to another directory (implies -i)",
            metavar="PATH",
        )
        action_group.add_argument(
            "--spawn",
            action=RtorrentInteractiveAction,
            help="execute OS command pattern(s) directly (implies -i)",
            metavar="CMD",
        )
        action_group.add_argument(
            "--flush",
            "-F",
            nargs=0,
            action=RtorrentAction,
            help="flush changes immediately (save session data)",
        )
        action_group.add_argument(
            "--ignore",
            action=RtorrentAction,
            choices=self.IGNORE_OPTIONS,
            help="set 'ignore commands' status on torrent",
        )
        action_group.add_argument(
            "--start",
            action=RtorrentAction,
            nargs=0,
            help="start torrent",
        )
        action_group.add_argument(
            "--stop",
            "--close",
            action=RtorrentAction,
            nargs=0,
            help="stop torrent",
        )
        action_group.add_argument(
            "--hash-check",
            "-H",
            action=RtorrentInteractiveAction,
            nargs=0,
            help="trigger a hash check (implies -i)",
        )
        action_group.add_argument(
            "--prio",
            action=RtorrentAction,
            choices=self.PRIO_OPTIONS,
            help="set priority of torrent",
        )
        action_group.add_argument(
            "--delete",
            action=RtorrentInteractiveAction,
            nargs=0,
            help="remove torrent (but not the data) (implies -i)",
        )
        action_group.add_argument(
            "--cull",
            action=RtorrentInteractiveAction,
            nargs=0,
            help="remove torrent and ALL data files (implies -i)",
        )
        action_group.add_argument(
            "--purge",
            action=RtorrentInteractiveAction,
            nargs=0,
            help="remove torrent and partial data files (implies -i)",
        )
        action_group.add_argument(
            "--throttle",
            "-T",
            const="set_throttle",
            action=RtorrentInteractiveAction,
            help="assign to named throttle group (NULL=unlimited, NONE=global) (implies -i)",
        )
        action_group.add_argument(
            "--tag",
            action=RtorrentInteractiveAction,
            metavar='"TAG +TAG -TAG..."',
            help="add or remove tag",
        )
        action_group.add_argument(
            "--custom",
            action=RtorrentAction,
            const="set_custom",
            metavar="KEY=VALUE",
            help="set value of 'custom_KEY' field (KEY might also be 1..5)",
        )
        action_group.add_argument(
            "--exec",
            "--rpc",
            action=RtorrentInteractiveAction,
            const="execute",
            metavar="RPC_CMD",
            help="execute RPC command pattern",
        )

    def format_item(self, item: str, defaults=None, stencil=None) -> str:
        """Format an item."""
        # pylint: disable=import-outside-toplevel
        from pyrosimple.torrent import rtorrent

        try:
            item_text: str = rtorrent.format_item(
                self.options.output_format_template, item, defaults
            )
        except (NameError, ValueError, TypeError) as exc:
            if self.LOG.isEnabledFor(logging.DEBUG):
                raise
            self.fatal(
                "Trouble with formatting item %r\n\n  FORMAT = %r\n\n  REASON ="
                % (item, self.options.output_format),
                exc,
            )

        if self.options.shell:
            item_text = "\t".join(shlex.quote(i) for i in item_text.split("\t"))

        # Justify headers according to stencil
        if stencil:
            item_text = "\t".join(
                i.ljust(len(s)) for i, s in zip(item_text.split("\t"), stencil)
            )

        return item_text

    def emit(
        self,
        item,
        defaults=None,
        stencil=None,
        to_log: Union[bool, Callable] = False,
        item_formatter=None,
    ):
        """Print an item to stdout, or the log on INFO level."""
        item_text: str = self.format_item(item, defaults, stencil)

        # Post-process line?
        if item_formatter:
            item_text = item_formatter(item_text)

        # Dump to selected target
        if to_log:
            if callable(to_log):
                to_log(item_text)
            else:
                self.LOG.info(item_text)
        elif self.options.nul:
            print(item_text, end="\0")
        else:
            print(item_text)

    def validate_output_format(self, default_format):
        """Prepare output format for later use."""
        # pylint: disable=import-outside-toplevel
        from pyrosimple import config
        from pyrosimple.torrent import rtorrent

        # pylint: enable=import-outside-toplevel

        output_format = self.options.output_format

        # Use default format if none is given
        if output_format is None:
            output_format = default_format

        # Check if it's a custom output format from configuration
        # (they take precedence over field names, so name them wisely)
        if output_format in config.settings.FORMATS:
            output_format = config.settings.FORMATS.get(output_format)

        # Expand plain field list to usable form
        # "name,size.sz" would become "{{d.name}}\t{{d.size|sz}}"
        if re.match(r"^[,._0-9a-zA-Z]+$", output_format):
            outputs = []
            for field in rtorrent.validate_field_list(
                output_format, allow_fmt_specs=True
            ):
                field = field.replace(".", "|")
                if len(field.split("|")) == 1:
                    outputs += [f"{{{{d.{field}|fmt('{field}')}}}}"]
                else:
                    outputs += ["{{d.%s}}" % field]
            output_format = "\t".join(outputs)

        # Replace some escape sequences
        output_format = (
            output_format.replace(r"\n", "\n")
            .replace(r"\t", "\t")
            .replace(r"\ ", " ")  # to prevent stripping in config file
        )
        self.options.output_format = output_format
        self.options.output_format_template = rtorrent.env.from_string(output_format)

    def get_output_fields(self) -> List[str]:
        """Get field names from output template."""
        from pyrosimple.torrent import (  # pylint: disable=import-outside-toplevel
            engine,
            rtorrent,
        )

        result = []
        for name in rtorrent.get_fields_from_template(self.options.output_format):
            if name not in engine.FIELD_REGISTRY:
                self.LOG.warning(
                    "Omitted unknown name '%s' from statistics and output format sorting",
                    name,
                )
            else:
                result.append(name)

        return result

    def validate_sort_fields(self):
        """Take care of sorting."""
        from pyrosimple import config  # pylint: disable=import-outside-toplevel
        from pyrosimple.torrent import (  # pylint: disable=import-outside-toplevel
            rtorrent,
        )

        if self.options.sort_fields is None:
            self.options.sort_fields = config.settings.SORT_FIELDS
        if self.options.sort_fields == "*":
            self.options.sort_fields = ",".join(self.get_output_fields())

        return rtorrent.validate_sort_fields(self.options.sort_fields)

    def show_in_view(self, sourceview, matches, targetname=None):
        """Show search result in ncurses view."""
        append = self.options.alter_view == "append"
        remove = self.options.alter_view == "remove"
        action_name = (
            ", appending to" if append else ", removing from" if remove else " into"
        )
        targetname = self.engine.show(
            matches,
            targetname or self.options.to_view or "rtcontrol",
            append=append,
            disjoin=remove,
        )
        msg = "Filtered %d out of %d torrents using [ %s ]" % (
            len(matches),
            sourceview.size(),
            sourceview.matcher,
        )
        self.LOG.info("%s%s rTorrent view %r.", msg, action_name, targetname)
        self.engine.log(msg)

    def mainloop(self):
        """The main loop."""
        if self.options.help_fields:
            print_help_fields()
            print_help_filters()
            sys.exit(0)

        # pylint: disable=import-outside-toplevel
        from pyrosimple import config
        from pyrosimple.torrent import rtorrent
        from pyrosimple.util import matching

        # pylint: enable=import-outside-toplevel
        # Print usage if no conditions are provided
        if not self.args:
            self.parser.error("No filter conditions given!")

        # Check special action options
        actions = getattr(self.options, "actions", [])

        # Reduce results according to index range
        selection = None
        if self.options.select:
            try:
                if "-" in self.options.select:
                    selection = tuple(
                        int(i or default, 10)
                        for i, default in zip(
                            self.options.select.split("-", 1), ("1", "-1")
                        )
                    )
                else:
                    selection = 1, int(self.options.select, 10)
            except (ValueError, TypeError) as exc:
                self.fatal(f"Bad selection '{self.options.select}' ({exc})")

        # Preparation steps
        if self.options.fast_query != "=":
            config.settings.set("FAST_QUERY", int(self.options.fast_query))
        # Set the output format
        raw_output_format = self.options.output_format
        default_output_format = "default"
        if actions:
            default_output_format = "action"
        self.validate_output_format(default_output_format)
        # Parse and validate sort fields
        sort_key = self.validate_sort_fields()
        # Get key names from the query
        query_tree = matching.QueryGrammar.parse(
            matching.cli_args_to_match_str(self.args)
        )
        key_names = matching.KeyNameVisitor().visit(query_tree)
        # Use validate_sort_fields to pre-validate key names
        rtorrent.validate_sort_fields(",".join(key_names))
        matcher = matching.MatcherBuilder().visit(query_tree)
        self.LOG.debug("Matcher is: %s", matcher)

        # View handling
        if self.options.modify_view:
            if self.options.from_view or self.options.to_view:
                self.fatal(
                    "You cannot combine --modify-view with --from-view or --to-view"
                )
            self.options.from_view = self.options.to_view = self.options.modify_view

        # Holds summary information, will be populated later
        summary = FieldStatistics()

        dcontext = None
        if self.options.detach:
            from daemon import DaemonContext  # pylint: disable=import-outside-toplevel

            dcontext = DaemonContext(
                detach_process=False,
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            dcontext.open()

        # Find matching torrents
        engines = {}
        for url in self.multi_connection_lookup(
            self.options.url or config.settings["SCGI_URL"]
        ):
            engines[url] = rtorrent.RtorrentEngine(url, auto_open=True)

        # Kick off the result fetcher in a thread pool
        pool = ThreadPool(processes=len(engines))
        futures = {}
        for url, r_engine in engines.items():

            def fetch(e):
                # pylint: disable=import-outside-toplevel
                from pyrosimple.torrent import engine

                view = e.view(self.options.from_view, matcher)
                prefetch = [
                    engine.FIELD_REGISTRY[f].requires
                    for f in self.get_output_fields()
                    + key_names
                    + [
                        s[1:] if s.startswith("-") else s
                        for s in self.options.sort_fields.split(",")
                    ]
                ]
                prefetch = [item for sublist in prefetch for item in sublist]
                matches = list(e.items(view=view, prefetch=prefetch))
                matches.sort(key=sort_key, reverse=self.options.reverse_sort)
                return matches

            futures[url] = pool.apply_async(fetch, (r_engine,))

        # The rest of the pipeline should still be done in sequence
        for url, r_engine in engines.items():
            view = r_engine.view(self.options.from_view, matcher)
            matches = futures[url].get()

            if selection:
                matches = matches[selection[0] - 1 : selection[1]]

            if not matches:
                # Think "404 NOT FOUND", but then exit codes should be < 256
                self.return_code = 44

            # Tee to ncurses view, if requested
            if self.options.tee_view and (
                self.options.to_view or self.options.view_only
            ):
                self.show_in_view(view, matches)

            # Generate summary?
            if self.options.stats or self.options.summary:
                for field in self.get_output_fields():
                    try:
                        0 + getattr(matches[0], field)
                    except (TypeError, ValueError, IndexError):
                        summary.total[field] = ""
                    else:
                        for item in matches:
                            summary.add(field, getattr(item, field))

            # Run actions?
            if actions:
                self.LOG.info(
                    "%s perform actions [%s] on %d out of %d torrents.",
                    "Would" if self.options.dry_run else "About to",
                    ",".join([a["method"] for a in actions]),
                    len(matches),
                    view.size(),
                )
            for item in matches:
                for action in actions:
                    action_name = action["method"].replace("_", " ")
                    defaults = {"action": action_name, "now": time.time}
                    defaults.update(self.FORMATTER_DEFAULTS)

                    args = action["args"]
                    # Templatetize arguments for some commands
                    if action_name in ["call", "spawn", "execute"]:
                        template_args = [
                            ("{##}" + i if "{{" in i else i) for i in action["args"]
                        ]
                        args = tuple(
                            rtorrent.format_item(
                                rtorrent.env.from_string(i),
                                item,
                                defaults=dict(item=item),
                            )
                            for i in template_args
                        )

                    if (
                        action["interactive"] or self.options.interactive
                    ) and not self.options.yes:
                        self.emit(item, defaults)
                        from prompt_toolkit import (  # pylint: disable=import-outside-toplevel
                            prompt,
                        )

                        answer = prompt(
                            f"{action_name}? [Y)es, n)o, a)ll yes, q)uit]: "
                        )
                        if answer.lower() in ["n", "no"]:
                            continue
                        if answer.lower() in ["q", "quit"]:
                            self.LOG.warning("Qutting due to user choice!")
                            sys.exit(error.EX_TEMPFAIL)
                        if answer.lower() in ["a", "all"]:
                            self.options.yes = True
                    elif (
                        self.options.output_format
                        and not self.options.view_only
                        and str(self.options.output_format) != "-"
                    ):
                        self.emit(item, defaults)

                    if self.options.dry_run:
                        self.LOG.debug("Would call action %s%r", action["method"], args)
                    else:
                        if action_name == "call":
                            self.LOG.debug("Calling '%s' with a shell", args[0])
                            subprocess.run(args[0], check=True, shell=True)
                            continue
                        if action_name == "spawn":
                            args = shlex.split(args[0])
                            self.LOG.debug("Spawning '%s'", args)
                            subprocess.run(args, check=True, shell=False)
                            continue
                        # Look up aliases when moving to a host
                        if action_name == "move to host":
                            args[0] = self.lookup_connection_alias(args[0])
                        getattr(item, action["method"])(*args)
                        if self.options.view_only:
                            show_in_client = functools.partial(
                                lambda x, e: e.open().log(rpc.NOHASH, x), e=r_engine
                            )
                            self.emit(item, defaults, to_log=show_in_client)

            # Show in ncurses UI?
            if not self.options.tee_view and (
                self.options.to_view or self.options.view_only
            ):
                self.show_in_view(view, matches)

            # Dump as JSON array?
            elif self.options.json:
                json_data = matches
                if raw_output_format:
                    json_fields = raw_output_format.split(",")
                    json_data = [
                        {name: getattr(i, name) for name in json_fields}
                        for i in matches
                    ]
                else:
                    from pyrosimple.torrent import (  # pylint: disable=import-outside-toplevel
                        engine,
                    )

                    json_data = [
                        {name: getattr(i, name) for name in engine.FIELD_REGISTRY}
                        for i in matches
                    ]
                json.dump(
                    json_data,
                    sys.stdout,
                    indent=2,
                    separators=(",", ": "),
                    sort_keys=True,
                    cls=pymagic.JSONEncoder,
                )
                sys.stdout.write("\n")
                sys.stdout.flush()

            # Show via template?
            elif self.options.output_template:
                full_ns = dict(
                    version=None,
                    proxy=r_engine.open(),
                    view=view,
                    query=matcher,
                    matches=matches,
                    summary=summary,
                )

                output_template = self.options.output_template
                sys.stdout.write(rtorrent.expand_template(output_template, full_ns))
                sys.stdout.flush()

            # Show on console?
            elif (
                self.options.output_format
                and str(self.options.output_format) != "-"
                and not actions
            ):
                if not self.options.summary:
                    for item in matches:
                        # Print matching item
                        self.emit(item, self.FORMATTER_DEFAULTS)

                # Print summary?
                if matches and summary:
                    print(f"TOTALS:\t{len(matches)} out of {view.size()} torrents")
                    self.emit(
                        summary.min, item_formatter=lambda i: "MIN:\t" + i.rstrip()
                    )
                    self.emit(
                        summary.average, item_formatter=lambda i: "AVG:\t" + i.rstrip()
                    )
                    self.emit(
                        summary.max, item_formatter=lambda i: "MAX:\t" + i.rstrip()
                    )
                    self.emit(
                        summary.total, item_formatter=lambda i: "SUM:\t" + i.rstrip()
                    )

                self.LOG.info(
                    "Displayed %d out of %d torrents.",
                    len(matches),
                    view.size(),
                )
            else:
                self.LOG.info(
                    "Filtered %d out of %d torrents.",
                    len(matches),
                    view.size(),
                )

            self.LOG.debug("RPC stats: %s", self.rpc_stats())
        if dcontext is not None:
            dcontext.close()


def run():  # pragma: no cover
    """The entry point."""
    RtorrentControl().run()


if __name__ == "__main__":
    run()
