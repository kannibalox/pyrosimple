# -*- coding: utf-8 -*-
# pylint: disable=attribute-defined-outside-init
""" Torrent Item Filters.

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
import fnmatch
import operator
import re
import time

from dataclasses import dataclass
from typing import Any, Callable, List

from parsimonious.grammar import Grammar
from parsimonious.nodes import NodeVisitor

from pyrosimple import config, error, torrent, util


TRUE = {
    "true",
    "t",
    "yes",
    "y",
    "1",
    "+",
}

FALSE = {
    "false",
    "f",
    "no",
    "n",
    "0",
    "-",
}


@dataclass
class FilterOperator:
    """Small class to hold operator information"""

    name: str
    query_repr: str


Operators = {
    "eq": FilterOperator("eq", "="),
    "ne": FilterOperator("ne", "!="),
    "gt": FilterOperator("gt", ">"),
    "lt": FilterOperator("lt", "<"),
    "ge": FilterOperator("ge", ">="),
    "le": FilterOperator("le", "<="),
}


def truth(val, context) -> bool:
    """Convert truth value in "val" to a boolean."""
    # Try coercing it to an int then a bool
    try:
        return bool(0 + val)
    except TypeError:
        pass

    lower_val = val.lower()

    if lower_val in TRUE:
        return True
    elif lower_val in FALSE:
        return False

    raise FilterError(
        "Bad boolean value %r in %r (expected one of '%s', or '%s')"
        % (val, context, "' '".join(TRUE), "' '".join(FALSE))
    )


def unquote_pre_filter(
    pre_filter: str, regex_: re.Pattern = re.compile(r"[\\]+")
) -> str:
    """Unquote a pre-filter condition."""
    if pre_filter.startswith('"') and pre_filter.endswith('"'):
        # Unquote outer level
        pre_filter = pre_filter[1:-1]
        pre_filter = regex_.sub(
            lambda x: x.group(0)[: len(x.group(0)) // 2], pre_filter
        )

    return pre_filter


class FilterError(error.UserError):
    """(Syntax) error in filter."""


class MatcherNode:
    """Base class for the tree structure."""

    def __init__(self, children: List):
        self.children = list(children)

    def match(self, item) -> bool:
        """Check if the item matches. All logic is deferred to subclasses."""
        raise NotImplementedError()

    def __repr__(self):
        result = type(self).__name__
        if self.children:
            result = str([str(c) for c in self.children])
        return result


class GroupNode(MatcherNode):
    """This simply groups another node, and optionally inverts it (a logical NOT)"""

    def __init__(self, children: List, invert: bool):
        super().__init__(children)
        self.invert = invert

    def match(self, item) -> bool:
        assert len(self.children) == 1
        result = bool(self.children[0].match(item))
        if self.invert:
            return not result
        return result

    def pre_filter(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        assert len(self.children) == 1
        inner = str(self.children[0].pre_filter())
        if self.invert:
            if inner.startswith('"not=$') and inner.endswith('"') and "\\" not in inner:
                return inner[6:-1]  # double negation, return inner command
            elif inner.startswith('"'):
                inner = '"$' + inner[1:]
            else:
                inner = "$" + inner
            return "not=" + inner
        return inner

    def __repr__(self):
        return f"{self.invert}{type(self).__name__}[{[str(c) for c in self.children]}]"


class AndNode(MatcherNode):
    """This node performs a logical AND for all of it's children."""

    def match(self, item) -> bool:
        return all(c.match(item) for c in self.children)

    def pre_filter(self):
        """Return rTorrent condition to speed up data transfer."""
        result = [x.pre_filter() for x in self.children]
        result = [x for x in result if x]
        if result:
            if int(config.settings.get("FAST_QUERY")) == 1 or len(result) == 1:
                return result[0]  # using just one simple expression is safer
            else:
                # TODO: make this purely value-based (is.nz=…)
                return "and={%s}" % ",".join(result)
        return ""


class OrNode(MatcherNode):
    """This node performs a logical OR for all of it's children."""

    def match(self, item) -> bool:
        return any(c.match(item) for c in self.children)

    def pre_filter(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        if int(config.settings.get("FAST_QUERY")) == 1:
            return ""
        if len(self.children) == 1:
            return str(self.children[0].pre_filter())
        else:
            result = [x.pre_filter() for x in self.children]
            result = [x for x in result if x]
            if result:
                # TODO: make this purely value-based (is.nz=…)
                return "or={%s}" % ",".join(result)
        return ""


class FieldFilter(MatcherNode):  # pylint: disable=abstract-method
    """Base class for all field filters.

    Subclasses of FieldFilter act as the leaves of the tree, providing
    matching and pre-filtering functionality."""

    PRE_FILTER_FIELDS = dict(
        # alias="",
        hash="d.hash=",
        name="d.name=",
        message="d.message=",
        metafile="d.tied_to_file=",
        path="d.base_path=",
        # realpath="=",
        throttle="d.throttle_name=",
        # tracker="=",
        is_active="d.is_active=",
        is_complete="d.complete=",
        is_ignored="d.ignore_commands=",
        is_multi_file="d.is_multi_file=",
        is_open="d.is_open=",
        # done="=",
        down="d.down.rate=",
        # fno="=",
        prio="d.priority=",
        ratio="d.ratio=",
        size="d.size_bytes=",
        up="d.up.rate=",
        uploaded="d.up.total=",
        completed="d.custom=tm_completed",
        loaded="d.custom=tm_loaded",
        started="d.custom=tm_started",
        # stopped="",
        custom_tm_completed="d.custom=tm_completed",
        custom_tm_loaded="d.custom=tm_loaded",
        custom_tm_started="d.custom=tm_started",
        # XXX: bad result: rtcontrol -Q2 -o- -v tagged='!'new,foo
        #       use a 'd.is_tagged=tag' command?
        tagged="d.custom=tags",
    )

    # active                last time a peer was connected
    # directory             directory containing download data
    # files                 list of files in this item
    # is_ghost              has no data file or directory?
    # is_private            private flag set (no DHT/PEX)?
    # leechtime             time taken from start to completion
    # seedtime              total seeding time after completion
    # traits                automatic classification of this item (audio, video, tv, movie, etc.)
    # views                 views this item is attached to
    # xfer                  transfer rate

    def __init__(self, name: str, op: FilterOperator, value: str):
        """Store field name and filter value for later evaluations."""
        super().__init__([])  # Filters are the leaves of the tree and have no children
        self._name = name
        self._condition = self._value = value
        self._op: FilterOperator = op

        self.validate()

    def __str__(self) -> str:
        return str(self._name) + self._op.query_repr + str(self._condition)

    def __call__(self, item):
        return self.match(item)

    def validate(self):
        """Validate filter condition (template method)."""

    # def pre_filter(self) -> str: # pylint: disable=no-self-use
    #     """Return a condition for use in d.multicall.filtered."""
    #     return ""

    def match(self, item) -> bool:
        """Test if item matches filter.

        By default this will defer to the operator functions in subclasses,
        but that behaivor can be overridden."""
        return bool(getattr(self, self._op.name)(item))

    def eq(self, item) -> bool:
        """Test equality against item"""
        raise FilterError(
            f"Filter '{type(self).__name__}' for field '{self._name}' does not support comparison '{self._op}'"
        )

    def gt(self, item) -> bool:
        """Test if item is greater than value"""
        raise FilterError(
            f"Filter '{type(self).__name__}' for field '{self._name}' does not support comparison '{self._op}'"
        )

    # Unfortunate but necessary boilerplate functions
    # pylint: disable=missing-function-docstring
    def ge(self, item) -> bool:
        return self.eq(item) or self.gt(item)

    def ne(self, item) -> bool:
        return not self.eq(item)

    def le(self, item) -> bool:
        return self.eq(item) or not self.gt(item)

    def lt(self, item) -> bool:
        return not self.eq(item) and not self.gt(item)

    # pylint: enable=missing-function-docstring

    def pre_filter(self) -> str:
        """Create a prefilter condition (if possible).

        By default this will defer to the operator functions in subclasses,
        but that behaivor can be overridden."""
        method_name = f"pre_filter_{self._op.name}"
        return str(getattr(self, method_name)())

    def pre_filter_eq(self) -> str:
        """Returns empty if not defined in subclass."""
        return ""

    def pre_filter_gt(self) -> str:
        """Returns empty if not defined."""
        return ""

    def pre_filter_ne(self) -> str:
        """Create a prefilter by creating a NOT[name=filter] object and rendering it."""
        if self.pre_filter_eq():
            return GroupNode(
                [type(self)(self._name, Operators["eq"], self._value)], True
            ).pre_filter()
        return ""


class PatternFilter(FieldFilter):
    """Case-insensitive pattern filter, either a glob or a /regex/ pattern."""

    CLEAN_PRE_VAL_RE = re.compile(r"(?:\[.*?]\])|(?:\(.*?]\))|(?:{.*?]})|(?:\\)")
    SPLIT_PRE_VAL_RE = re.compile(r"[^a-zA-Z0-9/_]+")
    SPLIT_PRE_GLOB_RE = re.compile(r"[?*]+")

    def validate(self):
        """Validate filter condition (template method)."""

        super().validate()
        self._value: str = self._value.lower()
        self._template = None
        self._matcher: Callable[Any, Any]
        if self._value.startswith("/") and self._value.endswith("/"):
            if self._value in ["//", "/.*/"]:
                self._matcher = lambda _, __: True
            else:
                regex = re.compile(self._value[1:-1])
                self._matcher = lambda val, _: regex.search(val)
        elif self._value.startswith("{{") or self._value.endswith("}}"):

            def _template_globber(val, item):
                """Helper."""
                pattern = torrent.formatting.format_item(torrent.formatting.env.from_string(self._template), item).replace(
                    "[", "[[]"
                )
                return fnmatch.fnmatchcase(val, pattern.lower())

            self._template = self._value
            self._matcher = _template_globber
        else:
            self._matcher = lambda val, _: fnmatch.fnmatchcase(val, self._value)

    def pre_filter_eq(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        if self._name not in self.PRE_FILTER_FIELDS or self._template:
            return ""
        if not self._value:
            return '"equal={},cat="'.format(self.PRE_FILTER_FIELDS[self._name])

        if self._value.startswith("/") and self._value.endswith("/"):
            needle = self._value[1:-1]
            needle = self.CLEAN_PRE_VAL_RE.sub(" ", needle)
            split_needle = self.SPLIT_PRE_VAL_RE.split(needle)
        else:
            needle = self.CLEAN_PRE_VAL_RE.sub(" ", self._value)
            split_needle = self.SPLIT_PRE_GLOB_RE.split(needle)
        needle = list(sorted(split_needle, key=len))[-1]

        if needle:
            try:
                needle.encode("ascii")
            except UnicodeEncodeError:
                return ""
            return r'"string.contains_i=${},\"{}\""'.format(
                self.PRE_FILTER_FIELDS[self._name], needle.replace('"', r"\\\"")
            )

        return ""

    def eq(self, item):
        """Return True if filter matches item."""
        val = (getattr(item, self._name) or "").lower()
        result = self._matcher(val, item)
        return result


class FilesFilter(PatternFilter):
    """Case-insensitive pattern filter on filenames in a torrent."""

    def match(self, item) -> bool:
        """Return True if filter matches item."""
        val = getattr(item, self._name)
        if val is not None:
            for fileinfo in val:
                if fnmatch.fnmatchcase(fileinfo.path.lower(), self._value):
                    return True
            return False
        return False


class TaggedAsFilter(FieldFilter):
    """Case-insensitive tags filter. Tag fields are white-space separated lists
    of tags.
    """

    def pre_filter(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        if self._name in self.PRE_FILTER_FIELDS:
            if not self._value:
                return '"not=${}"'.format(self.PRE_FILTER_FIELDS[self._name])
            else:
                val = self._value
                if self._exact:
                    val = val.split().pop()
                return r'"string.contains_i=${},\"{}\""'.format(
                    self.PRE_FILTER_FIELDS[self._name], val.replace('"', r"\\\"")
                )
        return ""

    def validate(self):
        """Validate filter condition (template method)."""
        super().validate()
        self._value = self._value.lower()

        # If the tag starts with '=', test on equality (just this tag, no others)
        if self._value.startswith("="):
            self._exact = True
            self._value = self._value[1:]
        else:
            self._exact = not self._value

        # For exact matches, value is the set to compare to
        if self._exact:
            # Empty tag means empty set, not set of one empty string
            self._value = set((self._value,)) if self._value else set()

    def match(self, item) -> bool:
        """Return True if filter matches item."""
        tags = getattr(item, self._name) or []
        if self._exact:
            # Equality check
            return self._value == set(tags)
        else:
            # Is given tag in list?
            return self._value in tags


class BoolFilter(FieldFilter):
    """Filter boolean values."""

    def pre_filter_eq(self):
        """Return rTorrent condition to speed up data transfer."""
        if self._name in self.PRE_FILTER_FIELDS:
            return '"equal={},value={}"'.format(
                self.PRE_FILTER_FIELDS[self._name], int(self._value)
            )
        return ""

    def validate(self):
        """Validate filter condition (template method)."""
        super().validate()

        self._value = truth(str(self._value), self._condition)
        self._condition = "yes" if self._value else "no"

    def eq(self, item):
        """Return True if filter matches item."""
        val = getattr(item, self._name) or False
        return bool(val) is self._value


class NumericFilterBase(FieldFilter):
    """Base class for numerical value filters."""

    def validate(self):
        """Validate filter condition (template method)."""
        super().validate()

        self.not_null = False

    def match(self, item) -> bool:
        """Return True if filter matches item."""
        val = getattr(item, self._name) or 0
        if self.not_null and self._value and not val:
            return False
        else:
            # Grab the function from the native operator module
            op = getattr(operator, self._op.name)
            return bool(op(float(val), self._value))


class FloatFilter(NumericFilterBase):
    """Filter float values."""

    FIELD_SCALE = dict(
        ratio=1000,
    )

    def pre_filter_eq(self):
        if self._name in self.PRE_FILTER_FIELDS:
            val = int(self._value * self.FIELD_SCALE.get(self._name, 1))
            return '"equal=value=${},value={}"'.format(
                self.PRE_FILTER_FIELDS[self._name], val
            )
        return ""

    def pre_filter_old(self):
        """Return rTorrent condition to speed up data transfer."""
        conditions = {"gt": "greater", "lt": "less", "eq": "equal"}
        if self._name in self.PRE_FILTER_FIELDS and self._op.name in conditions:
            val = int(self._value * self.FIELD_SCALE.get(self._name, 1))
            return '"{}=value=${},value={}"'.format(
                conditions[self._op.name], self.PRE_FILTER_FIELDS[self._name], val
            )
        return ""

    def validate(self):
        """Validate filter condition (template method)."""
        super().validate()

        try:
            self._value = float(self._value)
        except (ValueError, TypeError) as exc:
            raise FilterError(
                "Bad numerical value %r in %r (%s)"
                % (self._value, self._condition, exc)
            ) from exc


class TimeFilter(NumericFilterBase):
    """Filter UNIX timestamp values."""

    TIMEDELTA_UNITS = dict(
        y=lambda t, d: t - d * 365 * 86400,
        M=lambda t, d: t - d * 30 * 86400,
        w=lambda t, d: t - d * 7 * 86400,
        d=lambda t, d: t - d * 86400,
        h=lambda t, d: t - d * 3600,
        m=lambda t, d: t - d * 60,
        s=lambda t, d: t - d,
    )
    TIMEDELTA_RE = re.compile(
        "^%s$"
        % "".join(r"(?:(?P<%s>\d+)[%s%s])?" % (i, i, i.upper()) for i in "ymwdhis")
    )

    def pre_filter(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        if self._name in self.PRE_FILTER_FIELDS:
            # Adding a day of fuzz to avoid any possible timezone problems
            if self._op.name == "gt":
                timestamp = float(self._value) + 86400
                cmp_ = "greater"
            elif self._op.name == "lt":
                timestamp = float(self._value) - 86400
                cmp_ = "less"
            elif self._op.name == "eq":
                timestamp = 0
                cmp_ = "equal"
            else:
                return ""
            timestamp = float(self._value) + (
                -86400
                if self._op.name == "gt"
                else 86400
                if self._op.name == "lt"
                else 0
            )

            return '"{}=value=${},value={}"'.format(
                cmp_, self.PRE_FILTER_FIELDS[self._name], int(timestamp)
            )
        return ""

    def validate_time(self, duration=False):
        """Validate filter condition (template method) for timestamps and durations."""
        super().validate()
        timestamp = now = time.time()

        if str(self._value).isdigit():
            # Literal UNIX timestamp
            try:
                timestamp = float(self._value)
            except (ValueError, TypeError) as exc:
                raise FilterError(
                    "Bad timestamp value %r in %r" % (self._value, self._condition)
                ) from exc
        else:
            # Something human readable
            delta = self.TIMEDELTA_RE.match(self._value)
            if delta:
                # Time delta
                for unit, val in delta.groupdict().items():
                    if val:
                        timestamp = self.TIMEDELTA_UNITS[unit](timestamp, int(val, 10))

                if duration:
                    timestamp = now - timestamp
            else:
                # Assume it's an absolute date
                if "/" in self._value:
                    # U.S.
                    dtfmt = "%m/%d/%Y"
                elif "." in self._value:
                    # European
                    dtfmt = "%d.%m.%Y"
                else:
                    # Fall back to ISO
                    dtfmt = "%Y-%m-%d"

                val = str(self._value).upper().replace(" ", "T")
                if "T" in val:
                    # Time also given
                    dtfmt += "T%H:%M:%S"[: 3 + 3 * val.count(":")]

                try:
                    timestamp = time.mktime(tuple(time.strptime(val, dtfmt)))
                except (ValueError) as exc:
                    raise FilterError(
                        "Bad timestamp value %r in %r (%s)"
                        % (self._value, self._condition, exc)
                    ) from exc

                if duration:
                    timestamp -= now

        self._value = timestamp

    def validate(self):
        """Validate filter condition (template method)."""
        self.validate_time(duration=False)


class TimeFilterNotNull(TimeFilter):
    """Filter UNIX timestamp values, ignore unset values unless compared to 0."""

    def validate(self):
        """Validate filter condition (template method)."""
        super().validate()
        self.not_null = True


class DurationFilter(TimeFilter):
    """Filter durations in seconds."""

    def validate(self):
        """Validate filter condition (template method)."""
        super().validate_time(duration=True)

    def match(self, item) -> bool:
        """Return True if filter matches item."""
        if getattr(item, self._name) is None:
            # Never match "N/A" items, except when "-0" was specified
            return bool(self._value)
        else:
            return super().match(item)


class ByteSizeFilter(NumericFilterBase):
    """Filter size and bandwidth values."""

    UNITS = dict(b=1, k=1024, m=1024**2, g=1024**3)

    def pre_filter(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        comparers = {
            "gt": "greater",
            "lt": "less",
            "eq": "equal",
        }
        if self._name in self.PRE_FILTER_FIELDS and self._op.name in comparers:
            return '"{}={},value={}"'.format(
                comparers[self._op.name],
                self.PRE_FILTER_FIELDS[self._name],
                int(self._value),
            )
        return ""

    def validate(self):
        """Validate filter condition (template method)."""
        super().validate()

        # Get scale
        lower_val = str(self._value).lower()
        if any(lower_val.endswith(i) for i in self.UNITS):
            scale = self.UNITS[lower_val[-1]]
            self._value = self._value[:-1]
        else:
            scale = 1

        # Get float value
        try:
            self._value = float(self._value)
        except (ValueError, TypeError) as exc:
            raise FilterError(
                "Bad numerical value %r in %r" % (self._value, self._condition)
            ) from exc

        # Scale to bytes
        self._value = self._value * scale


QueryGrammar = Grammar(
    r"""
    query = (group / stmt)+
    group = (not ws)? lpar ws stmt ws rpar
    stmt = (or_stmt / conds)
    or_stmt = conds ws or ws conds
    conds = cond (ws cond)*
    cond = (&or / &lpar / &rpar / &not / named_cond / unnamed_cond)
    named_cond = word conditional filter
    unnamed_cond = filter
    filter      = (glob / regex / quoted / word)
    glob = ~r"[*\.\/{}|\-?!\w]+"
    regex = ~"/[^/]*/"
    quoted      = ~'"[^\"]*"'
    word        = ~r"[\w]+"
    conditional = (ne / ge / le / lt / gt / eq)
    ne          = ("!=" / "<>")
    eq          = ("==" / "=")
    gt          = ">"
    lt          = "<"
    ge          = (">=" / "=+")
    le          = ("<=" / "=-")
    fws         = ~r"\s+"
    ws          = ~r"\s*"
    lpar = "["
    rpar = "]"
    or = "OR"
    not = ( "NOT" / "!" )
    """
)


class KeyNameVisitor(NodeVisitor):
    """Walk through a query tree and returns an array of key names.
    Implicit key names are not included."""

    # pylint: disable=no-self-use,unused-argument,missing-function-docstring
    def visit_expr(self, node, visited_children):
        output = ""
        for child in visited_children:
            output += str(child)
        return output

    def visit_named_cond(self, node, visited_children):
        return visited_children[0]

    def visit_word(self, node, visited_children):
        return [node.text]

    def generic_visit(self, node, visited_children):
        if visited_children:
            return [item for sublist in visited_children for item in sublist]
        else:
            return []


def create_filter(name: str, op: str, value: str):
    """Generates a filter class with the given name, operation and value"""
    filt = torrent.engine.FieldDefinition.lookup(name)._matcher
    return filt(name, op, value)


class MatcherBuilder(NodeVisitor):
    """Build a simplified tree of MatcherNodes to match an item against."""

    # pylint: disable=no-self-use,unused-argument,missing-function-docstring
    def visit_named_cond(self, node, visited_children):
        key, cond, needle = visited_children
        return create_filter(key, cond, needle)

    def visit_group(self, node, visited_children):
        return GroupNode(
            [c for c in visited_children[1:] if c is not None], visited_children[0]
        )

    def visit_not(self, node, visited_children):
        if node.text:
            return True
        return False

    def __pare_children(self, children, class_):
        """Get all non-None children, and if there's only one child left,
        return the child instead of wrapping it in the parent class.

        We should hopefully never have to deal with all None children,
        due to the grammar combined with the generic_visit method.
        """
        real_children = [c for c in children if c is not None]
        if len(real_children) == 1:
            return real_children[0]
        return class_(real_children)

    def visit_or_stmt(self, node, visited_children):
        return self.__pare_children(visited_children, OrNode)

    def visit_conds(self, node, visited_children):
        if len(visited_children) == 2 and isinstance(visited_children[1], list):
            children = [visited_children[0]] + visited_children[1]
        else:
            children = visited_children
        return self.__pare_children(children, AndNode)

    def visit_cond(self, node, visited_children):
        if len(visited_children) == 1 and isinstance(
            visited_children[0], (str, re.Pattern)
        ):
            return create_filter("name", Operators["eq"], visited_children[0])
        return self.generic_visit(node, visited_children)

    # Unfortunate but necessary boilerplate methods

    def visit_word(self, node, visited_children):
        return node.text

    def visit_quoted(self, node, visited_children):
        return node.text[1:-1]

    def visit_glob(self, node, visited_children):
        return node.text

    def visit_regex(self, node, visited_children):
        return node.text

    def visit_eq(self, node, visited_children):
        return Operators["eq"]

    def visit_ne(self, node, visited_children):
        return Operators["ne"]

    def visit_gt(self, node, visited_children):
        return Operators["gt"]

    def visit_ge(self, node, visited_children):
        return Operators["ge"]

    def visit_lt(self, node, visited_children):
        return Operators["lt"]

    def visit_le(self, node, visited_children):
        return Operators["le"]

    def generic_visit(self, node, visited_children):
        real_children = [c for c in visited_children if c is not None]
        if real_children:
            if isinstance(real_children, list) and len(real_children) == 1:
                return real_children[0]
            return real_children
        else:
            return None


if __name__ == "__main__":
    tree = QueryGrammar.parse("name=/asdfsd/ OR /.*/ tagged=test2")
    print(tree)
    match_tree = MatcherBuilder().visit(tree)
    print(match_tree)
    match_result = match_tree.match(util.parts.Bunch(tagged="test", name="The Thing"))
    print(match_result)
