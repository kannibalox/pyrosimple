# -*- coding: utf-8 -*-
# pylint: disable=no-self-use,too-many-lines,too-many-nested-blocks
""" rTorrent Control.

    Copyright (c) 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
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

import json
import re
import shlex
import subprocess
import sys
import time

from typing import Callable, List, Optional, Union

from pyrosimple import config, error
from pyrosimple.scripts.base import PromptDecorator, ScriptBase, ScriptBaseWithConfig
from pyrosimple.torrent import engine, formatting
from pyrosimple.util import matching, pymagic, rpc
from pyrosimple.util.parts import Bunch, DefaultBunch


def print_help_fields():
    """Print help about fields and field formatters."""
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
        (
            "\n".join(
                [
                    "  %-21s %s" % (name, field.__doc__)
                    for name, field in sorted(
                        list(engine.FieldDefinition.FIELDS.items())
                        + [
                            custom_manifold(),
                            kind_manifold(),
                        ]
                    )
                ]
            )
        )
    )


class FieldStatistics:
    """Collect statistical values for the fields of a search result."""

    def __init__(self, size):
        "Initialize accumulator"
        self.size = size
        self.errors = DefaultBunch(int)
        self.total = DefaultBunch(int)
        self.min = DefaultBunch(int)
        self.max = DefaultBunch(int)
        self._basetime = time.time()

    def __bool__(self):
        "Truth"
        return bool(self.total)

    def __nonzero__(self):
        return self.__bool__()

    def add(self, field, val):
        "Add a sample"
        if engine.FieldDefinition.FIELDS[field]._matcher is matching.TimeFilter:
            val = self._basetime - val

        try:
            self.total[field] += val
            self.min[field] = min(self.min[field], val) if field in self.min else val
            self.max[field] = max(self.max[field], val)
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
        # for key, fielddef in  engine.FieldDefinition.FIELDS.items():
        #    if key in result and fielddef._matcher is matching.TimeFilter:
        #       result[key] = ''
        # for key, fielddef in  engine.FieldDefinition.FIELDS.items():
        #    if key in result and fielddef._matcher is matching.TimeFilter:
        #        result[key] = engine._fmt_duration(result[key])
        # print self.total
        # print result
        return result


class RtorrentControl(ScriptBaseWithConfig):
    ### Keep things wrapped to fit under this comment... ##############################
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

    See https://pyrosimple.readthedocs.io/en/latest/usage.html#rtcontrol for more.

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

    # additonal stuff appended after the command handler's docstring
    ADDITIONAL_HELP = [
        "",
        "",
        "Use --help to get a list of all options.",
        "Use --help-fields to list all fields and their description.",
    ]

    # additional values for output formatting
    FORMATTER_DEFAULTS = dict(
        now=time.time(),
    )

    # choices for --ignore
    IGNORE_OPTIONS = ("0", "1")

    # choices for --prio
    PRIO_OPTIONS = ("0", "1", "2", "3")

    # choices for --alter
    ALTER_MODES = ("append", "remove")

    # action options that perform some change on selected items
    ACTION_MODES = (
        Bunch(name="start", options=("--start",), help="start torrent"),
        Bunch(
            name="close",
            options=("--close", "--stop"),
            help="stop torrent",
            method="stop",
        ),
        Bunch(
            name="hash_check",
            label="HASH",
            options=("-H", "--hash-check"),
            help="hash-check torrent",
            interactive=True,
        ),
        # TODO: Bunch(name="announce", options=("--announce",), help="announce right now", interactive=True),
        # TODO: --pause, --resume?
        # TODO: implement --clean-partial
        # self.add_bool_option("--clean-partial",
        #    help="remove partially downloaded 'off'ed files (also stops downloads)")
        Bunch(
            name="delete",
            options=("--delete",),
            help="remove torrent from client",
            interactive=True,
        ),
        Bunch(
            name="purge",
            options=("--purge", "--delete-partial"),
            help="delete PARTIAL data files and remove torrent from client",
            interactive=True,
        ),
        Bunch(
            name="cull",
            options=("--cull", "--exterminate", "--delete-all"),
            help="delete ALL data files and remove torrent from client",
            interactive=True,
        ),
        Bunch(
            name="throttle",
            options=(
                "-T",
                "--throttle",
            ),
            argshelp="NAME",
            method="set_throttle",
            help="assign to named throttle group (NULL=unlimited, NONE=global)",
            interactive=True,
        ),
        Bunch(
            name="tag",
            options=("--tag",),
            argshelp='"TAG +TAG -TAG..."',
            help="add or remove tag(s)",
            interactive=False,
        ),
        Bunch(
            name="custom",
            label="SET_CUSTOM",
            options=("--custom",),
            argshelp="KEY=VALUE",
            method="set_custom",
            help="set value of 'custom_KEY' field (KEY might also be 1..5)",
            interactive=False,
        ),
        Bunch(
            name="exec",
            label="EXEC",
            options=("--exec", "--xmlrpc", "--RPC"),
            argshelp="CMD",
            method="execute",
            help="execute RPC command pattern",
            interactive=True,
        ),
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

    def __init__(self):
        """Initialize rtcontrol."""
        super().__init__()

        self.prompt = PromptDecorator(self)
        self.is_plain_output_format = False
        self.original_output_format = None

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
        self.prompt.add_options()

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
            "-c", "--column-headers", help="print column headers", action="store_true"
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
            metavar="LEVEL",
            default="=",
            choices=("=", "0", "1", "2"),
            help="enable query optimization (=: use config; 0: off; 1: safe; 2: danger seeker)",
        )
        action_group = self.parser.add_argument_group("actions")
        action_group.add_argument(
            "--call",
            metavar="CMD [--call]",
            action="append",
            default=[],
            help="call an OS command pattern in the shell",
        )
        action_group.add_argument(
            "--spawn",
            metavar="CMD [--spawn ...]",
            action="append",
            default=[],
            help="execute OS command pattern(s) directly",
        )
        action_group.add_argument(
            "-F",
            "--flush",
            help="flush changes immediately (save session data)",
            action="store_true",
        )

        # torrent state change (actions)
        for action in self.ACTION_MODES:
            action.setdefault("label", action.name.upper())
            action.setdefault("method", action.name)
            action.setdefault("interactive", False)
            action.setdefault("argshelp", "")
            action.setdefault("args", ())
            if action.argshelp:
                action_group.add_argument(
                    *action.options,
                    **{
                        "metavar": action.argshelp,
                        "help": action.help
                        + (" (implies -i)" if action.interactive else ""),
                    },
                )
            else:
                action_group.add_argument(
                    *action.options,
                    **{
                        "action": "store_true",
                        "help": action.help
                        + (" (implies -i)" if action.interactive else ""),
                    },
                )
        action_group.add_argument(
            "--ignore",
            choices=self.IGNORE_OPTIONS,
            help="set 'ignore commands' status on torrent",
        )
        action_group.add_argument(
            "--prio",
            choices=self.PRIO_OPTIONS,
            help="set priority of torrent",
        )

    def help_completion_fields(self):
        """Return valid field names."""
        for name, field in sorted(engine.FieldDefinition.FIELDS.items()):
            if issubclass(field._matcher, matching.BoolFilter):
                yield "%s=no" % (name,)
                yield "%s=yes" % (name,)
                continue
            if issubclass(field._matcher, matching.PatternFilter):
                yield "%s=" % (name,)
                yield "%s=/" % (name,)
                yield "%s=?" % (name,)
                yield "%s=\"'*'\"" % (name,)
                continue
            if issubclass(field._matcher, matching.NumericFilterBase):
                for i in range(10):
                    yield "%s=%d" % (name, i)
            else:
                yield "%s=" % (name,)

            yield r"%s=+" % (name,)
            yield r"%s=-" % (name,)

        yield "custom_"
        yield "kind_"

    # TODO: refactor to engine.TorrentProxy as format() method
    def format_item(self, item: str, defaults=None, stencil=None) -> str:
        """Format an item."""

        try:
            item_text: str = formatting.format_item(
                self.options.output_format_template, item, defaults
            )
        except (NameError, ValueError, TypeError) as exc:
            self.fatal(
                "Trouble with formatting item %r\n\n  FORMAT = %r\n\n  REASON ="
                % (item, self.options.output_format),
                exc,
            )
            raise  # in --debug mode

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

    # TODO: refactor to formatting.OutputMapping as a class method
    def validate_output_format(self, default_format):
        """Prepare output format for later use."""
        output_format = self.options.output_format
        self.original_output_format = output_format

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
            self.is_plain_output_format = True
            outputs = []
            for field in formatting.validate_field_list(
                output_format, allow_fmt_specs=True
            ):
                field = field.replace(".", "|")
                if len(field.split("|")) == 1:
                    outputs += ["{{d.%s|fmt('%s')}}" % (field, field)]
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
        self.options.output_format_template = formatting.env.from_string(output_format)

    # TODO: refactor to engine.FieldDefinition as a class method
    def get_output_fields(self) -> List[str]:
        """Get field names from output template."""
        result = []
        for name in formatting.get_fields_from_template(self.options.output_format):
            if name not in engine.FieldDefinition.FIELDS:
                self.LOG.warning(
                    "Omitted unknown name '%s' from statistics and output format sorting",
                    name,
                )
            else:
                result.append(name)

        return result

    def validate_sort_fields(self):
        """Take care of sorting."""
        if self.options.sort_fields is None:
            self.options.sort_fields = config.settings.SORT_FIELDS
        if self.options.sort_fields == "*":
            self.options.sort_fields = self.get_output_fields()

        return formatting.validate_sort_fields(self.options.sort_fields)

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
        # Print field definitions?
        if self.options.help_fields:
            self.parser.print_help()
            print_help_fields()
            sys.exit(1)

        # Print usage if no conditions are provided
        if not self.args:
            self.parser.error("No filter conditions given!")

        # Check special action options
        actions = []
        if self.options.ignore:
            actions.append(
                Bunch(
                    name="ignore",
                    method="ignore",
                    label="IGNORE" if int(self.options.ignore) else "HEED",
                    help="commands on torrent",
                    interactive=False,
                    args=(self.options.ignore,),
                )
            )
        if self.options.prio:
            actions.append(
                Bunch(
                    name="prio",
                    method="set_prio",
                    label="PRIO" + str(self.options.prio),
                    help="for torrent",
                    interactive=False,
                    args=(self.options.prio,),
                )
            )

        # Check standard action options
        # TODO: Allow certain combinations of actions (like --tag foo --stop etc.)
        #       How do we get a sensible order of execution?
        for action_mode in self.ACTION_MODES:
            if getattr(self.options, action_mode.name):
                if actions:
                    self.parser.error(
                        "Options --%s and --%s are mutually exclusive"
                        % (
                            ", --".join(i.name.replace("_", "-") for i in actions),
                            action_mode.name.replace("_", "-"),
                        )
                    )
                if action_mode.argshelp:
                    action_mode.args = (getattr(self.options, action_mode.name),)
                actions.append(action_mode)
        if not actions and self.options.flush:
            actions.append(
                Bunch(
                    name="flush",
                    method="flush",
                    label="FLUSH",
                    help="flush session data",
                    interactive=False,
                    args=(),
                )
            )
            self.options.flush = False  # No need to flush twice
        if any(i.interactive for i in actions):
            self.options.interactive = True

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
                self.fatal("Bad selection '%s' (%s)" % (self.options.select, exc))

        # Preparation steps
        if self.options.fast_query != "=":
            config.settings.set("FAST_QUERY", int(self.options.fast_query))
        raw_output_format = self.options.output_format
        default_output_format = "default"
        if actions:
            default_output_format = "action"
        self.validate_output_format(default_output_format)
        sort_key = self.validate_sort_fields()
        query_tree = matching.QueryGrammar.parse(" ".join(self.args))
        matcher = matching.MatcherBuilder().visit(query_tree)
        self.LOG.debug("Matcher is: %s", matcher)

        # View handling
        if self.options.modify_view:
            if self.options.from_view or self.options.to_view:
                self.fatal(
                    "You cannot combine --modify-view with --from-view or --to-view"
                )
            self.options.from_view = self.options.to_view = self.options.modify_view

        # Find matching torrents
        view = self.engine.view(self.options.from_view, matcher)
        prefetch = [
            engine.FieldDefinition.FIELDS[f].requires
            for f in self.get_output_fields()
            + matching.KeyNameVisitor().visit(query_tree)
            + [
                s[1:] if s.startswith("-") else s
                for s in self.options.sort_fields.split(",")
            ]
        ]
        prefetch = [item for sublist in prefetch for item in sublist]
        matches = list(self.engine.items(view=view, prefetch=prefetch))
        matches.sort(key=sort_key, reverse=self.options.reverse_sort)

        if selection:
            matches = matches[selection[0] - 1 : selection[1]]

        if not matches:
            # Think "404 NOT FOUND", but then exit codes should be < 256
            self.return_code = 44

        # Build header stencil
        stencil: Optional[str] = None
        if self.options.column_headers and self.is_plain_output_format and matches:
            stencil = formatting.format_item(
                self.options.output_format_template, matches[0], self.FORMATTER_DEFAULTS
            ).split("\t")
            self.emit(item=None, stencil=stencil)

        # Tee to ncurses view, if requested
        if self.options.tee_view and (self.options.to_view or self.options.view_only):
            self.show_in_view(view, matches)

        # Generate summary?
        summary = FieldStatistics(len(matches))
        if self.options.stats or self.options.summary:
            for field in self.get_output_fields():
                try:
                    0 + getattr(matches[0], field)
                except (TypeError, ValueError, IndexError):
                    summary.total[field] = ""
                else:
                    for item in matches:
                        summary.add(field, getattr(item, field))

        def output_formatter(templ, namespace=None):
            "Output formatting helper"
            full_ns = dict(
                version=None,
                proxy=self.engine.open(),
                view=view,
                query=matcher,
                matches=matches,
                summary=summary,
            )
            full_ns.update(namespace or {})
            return formatting.expand_template(templ, full_ns)

        # Execute action?
        if actions:
            action = actions[0]  # TODO: loop over it
            self.LOG.info(
                "%s %s %d out of %d torrents.",
                "Would" if self.options.dry_run else "About to",
                action.label,
                len(matches),
                view.size(),
            )
            defaults = {"action": action.label, "now": time.time}
            defaults.update(self.FORMATTER_DEFAULTS)

            if self.options.column_headers and matches:
                self.emit(None, stencil=stencil)

            # Perform chosen action on matches
            template_args = [("{##}" + i if "{{" in i else i) for i in action.args]
            for item in matches:
                if not self.prompt.ask_bool("%s item %s" % (action.label, item.name)):
                    continue
                if (
                    self.options.output_format
                    and not self.options.view_only
                    and str(self.options.output_format) != "-"
                ):
                    self.emit(item, defaults)

                args = tuple(
                    formatting.format_item(
                        formatting.env.from_string(i), item, defaults=dict(item=item)
                    )
                    for i in template_args
                )

                if self.options.dry_run:
                    if self.options.debug:
                        self.LOG.debug("Would call action %s(*%r)", action.method, args)
                else:
                    getattr(item, action.method)(*args)
                    if self.options.flush:
                        item.flush()
                    if self.options.view_only:
                        show_in_client = lambda x: self.engine.open().log(rpc.NOHASH, x)
                        self.emit(item, defaults, to_log=show_in_client)

        # Show in ncurses UI?
        elif not self.options.tee_view and (
            self.options.to_view or self.options.view_only
        ):
            self.show_in_view(view, matches)

        # Execute OS commands?
        elif self.options.call or self.options.spawn:
            if self.options.call and self.options.spawn:
                self.fatal("You cannot mix --call and --spawn")

            template_cmds = []
            if self.options.call:
                for cmd in self.options.call:
                    template_cmds.append(["{##}" + cmd])
            else:
                for cmd in self.options.spawn:
                    template_cmds.append(
                        [
                            ("{##}" + i if "{{" in i else i)
                            for i in shlex.split(str(cmd))
                        ]
                    )

            for item in matches:
                cmds: List[str] = [
                    [formatting.format_item(i, item) for i in k] for k in template_cmds
                ]

                if self.options.dry_run:
                    self.LOG.info("Would call command(s) %r", cmds)
                else:
                    for cmd in cmds:
                        if self.options.call:
                            logged_cmd = cmd[0]
                        else:
                            logged_cmd = '"%s"' % ('" "'.join(cmd),)
                        self.LOG.info("Calling: %s", logged_cmd)
                        try:
                            if self.options.call:
                                subprocess.check_call(cmd[0], shell=True)
                            else:
                                subprocess.check_call(cmd)
                        except subprocess.CalledProcessError as exc:
                            raise error.UserError("Command failed: %s" % (exc,))
                        except OSError as exc:
                            raise error.UserError(
                                "Command failed (%s): %s"
                                % (
                                    logged_cmd,
                                    exc,
                                )
                            )

        # Dump as JSON array?
        elif self.options.json:
            json_data = matches
            if raw_output_format:
                json_fields = raw_output_format.split(",")
                json_data = [
                    {name: getattr(i, name) for name in json_fields} for i in matches
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
            output_template = self.options.output_template
            sys.stdout.write(output_formatter(output_template))
            sys.stdout.flush()

        # Show on console?
        elif self.options.output_format and str(self.options.output_format) != "-":
            if not self.options.summary:
                for item in matches:
                    # Print matching item
                    self.emit(item, self.FORMATTER_DEFAULTS)

            # Print summary?
            if matches and summary:
                print(f"TOTALS:\t{len(matches)} out of {view.size()} torrents")
                self.emit(summary.min, item_formatter=lambda i: "MIN:\t" + i.rstrip())
                self.emit(
                    summary.average, item_formatter=lambda i: "AVG:\t" + i.rstrip()
                )
                self.emit(summary.max, item_formatter=lambda i: "MAX:\t" + i.rstrip())
                self.emit(summary.total, item_formatter=lambda i: "SUM:\t" + i.rstrip())

            self.LOG.info(
                "Dumped %d out of %d torrents.",
                len(matches),
                view.size(),
            )
        else:
            self.LOG.info(
                "Filtered %d out of %d torrents.",
                len(matches),
                view.size(),
            )

        self.LOG.debug("RPC stats: %s", self.engine.rpc)


def run():  # pragma: no cover
    """The entry point."""
    ScriptBase.setup()
    RtorrentControl().run()


if __name__ == "__main__":
    run()
