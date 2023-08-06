"""Torrent Item Filters.

Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>

There's a lot of magic going on in this module, but essentially
its primary responsibility is parsing queries from rtcontrol and other
places. Once parsed, it uses the visitor pattern in some classes to do
things like return lists of the fields being referenced, prepare
d.multicall.filtered statements or check if it matches against an
actual item.
"""


import fnmatch
import math
import operator
import re
import time

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Union

from parsimonious.grammar import Grammar
from parsimonious.nodes import NodeVisitor

from pyrosimple import config, error, torrent


TRUE = {
    "true",
    "t",
    "yes",
    "y",
    "1",
}

FALSE = {
    "false",
    "f",
    "no",
    "n",
    "0",
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


def truth(val: Any, context="statement") -> bool:
    """Convert truth value in "val" to a boolean."""
    # Try coercing it to an int then a bool
    try:
        return bool(0 + val)
    except TypeError:
        pass

    lower_val = val.lower()

    if lower_val in TRUE:
        return True
    if lower_val in FALSE:
        return False

    raise FilterError(
        f"Bad boolean value {val!r} in {context!r} (expected one of '{TRUE}', or '{FALSE}')"
    )


TIMEDELTA_UNITS = {
    "y": lambda d: d * 365 * 86400,
    "M": lambda d: d * 30 * 86400,
    "w": lambda d: d * 7 * 86400,
    "d": lambda d: d * 86400,
    "h": lambda d: d * 3600,
    "m": lambda d: d * 60,
    "s": lambda d: d,
}
TIMEDELTA_RE = re.compile(
    "^" + "".join(r"(?:(?P<{0}>\d+)[{0}{0}])?".format(i) for i in "yMwdhms") + "$"
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
        self.invert = bool(invert)

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
            if inner.startswith('"'):
                inner = '"$' + inner[1:]
            else:
                inner = "$" + inner
            return "not=" + inner
        return inner

    def __repr__(self):
        prefix = "Not" if self.invert else ""
        return f"{prefix}{type(self).__name__}{[repr(c) for c in self.children]}"


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
            return f'and={",".join(result)}'
        return ""

    def __repr__(self):
        return f"{type(self).__name__}{[repr(c) for c in self.children]}"


class OrNode(MatcherNode):
    """This node performs a logical OR for all of it's children."""

    def match(self, item) -> bool:
        return any(c.match(item) for c in self.children)

    def pre_filter(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        if len(self.children) == 1:
            return str(self.children[0].pre_filter())
        if int(config.settings.get("FAST_QUERY")) == 1:
            return ""
        result = [x.pre_filter() for x in self.children]
        result = [x for x in result if x]
        if result:
            return f'or={",".join(result)}'
        return ""

    def __repr__(self):
        return f"{type(self).__name__}{[repr(c) for c in self.children]}"


class FieldFilter(MatcherNode):
    """Base class for all field filters.

    Subclasses of FieldFilter act as the leaves of the tree, providing
    matching and pre-filtering functionality."""

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
    # This makes it so that by default all operators are available to fields
    # If there's a more effecient way to implement it for a specific subclass, it needs
    # to happen in there.
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
        but that behavior can be overridden."""
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
    """Pattern filter, either a glob or a /regex/ pattern."""

    CLEAN_PRE_VAL_RE = re.compile(r"(?:\[.*?\])|(?:\(.*?\))|(?:{.*?})|(?:\\)")
    SPLIT_PRE_VAL_RE = re.compile(r"[^a-zA-Z0-9/_]+")
    SPLIT_PRE_GLOB_RE = re.compile(r"[?*[\]]+")

    def validate(self) -> None:
        """Validate filter condition (template method)."""

        super().validate()
        self._value: str = self._value
        self._template = None
        self._flags = 0
        self._matcher: Callable[[str, Any], bool]
        if (
            self._value == '""'
        ):  # Replace an empty string with a simple truthiness check
            self._matcher = lambda val, _: val == ""
        elif self._value.startswith("/") and (
            self._value.endswith("/") or self._value.endswith("/i")
        ):
            # Pick out a couple regexes that can be simplified
            if self._value in ["//", "/.*/", "//i", "/.*/i"]:
                self._matcher = lambda _, __: True
            elif self._value in ["/.+/", "/.+/i"]:
                self._matcher = lambda val, __: bool(val)
            # Otherwise handle it generically
            else:
                value = self._value
                if self._value.endswith("/i"):
                    self._flags = re.IGNORECASE
                    value = self._value.rstrip("i")
                regex = re.compile(value[1:-1], self._flags)
                self._matcher = lambda val, _: bool(regex.search(val))
        elif self._value.startswith("{{") or self._value.endswith("}}"):
            self._template = self._value

            def _template_globber(val, item) -> bool:
                """Helper method to allow templating a glob."""
                if self._template is not None:
                    pattern = torrent.rtorrent.format_item(
                        torrent.rtorrent.env.from_string(self._template), item
                    )
                    return fnmatch.fnmatchcase(val, pattern)
                return False

            self._matcher = _template_globber
        else:
            # Pick out a glob that can be simplified
            if self._value == "*":
                self._matcher = lambda _, __: True
            else:
                self._matcher = (
                    lambda val, _: fnmatch.fnmatchcase(val, self._value)
                    or val == self._value
                )

    def pre_filter_eq(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        pf = prefilter_field_lookup(self._name)
        if pf is None or self._template:
            return ""
        if not self._value or self._value == '""':
            return f'"equal={pf},cat="'

        if self._value.startswith("/") and (
            self._value.endswith("/") or self._value.endswith("/i")
        ):
            if self._value.endswith("/i"):
                needle = self._value[1:-2]
            else:
                needle = self._value[1:-1]
            needle = self.CLEAN_PRE_VAL_RE.sub(" ", needle)
            split_needle = self.SPLIT_PRE_VAL_RE.split(needle)
            # If the cleaning of the needle did not succeed and we still
            # have regex-y values, don't prefilter
            if any(metachar in needle for metachar in r"{}[]\\|()"):
                return ""
        else:
            split_needle = self.SPLIT_PRE_GLOB_RE.split(self._value)
        # Grab the longest needle available from the array
        needle = list(sorted(split_needle, key=len))[-1]

        if needle:
            # Skip trying to filter on non-ASCII characters
            try:
                needle.encode("ascii")
            except UnicodeEncodeError:
                return ""
            needle = needle.replace('"', r"\\\"")
            return rf'"string.contains_i=${pf},\"{needle}\""'

        return ""

    def eq(self, item):
        """Return True if filter matches item."""
        val = getattr(item, self._name) or ""
        result = self._matcher(val, item)
        return result


class FilesFilter(PatternFilter):
    """Pattern filter on filenames in a torrent."""

    def match(self, item) -> bool:
        """Return True if filter matches item. Overridden from the
        parent class to deal with with an array of strings rather than
        a single string
        """
        val = getattr(item, self._name)
        if val is not None:
            for fileinfo in val:
                if fnmatch.fnmatchcase(fileinfo.path, self._value):
                    return True
            return False
        return False


class TaggedAsFilter(FieldFilter):
    """Case-insensitive tags filter. Tag fields are white-space
    separated lists of tags.
    """

    def pre_filter_eq(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        pf = prefilter_field_lookup(self._name)
        if pf is not None:
            if self._exact and not self._value:
                return f'"equal={pf},cat="'
            if not self._value:
                return f'"not=${pf}"'
            needle = self._value.replace('"', r"\\\"")
            return rf'"string.contains_i=${pf},\"{needle}\""'
        return ""

    def validate(self):
        """Validate filter condition (template method)."""
        super().validate()
        self._value = self._value.lower()

        # If the tag starts with ':', test for exact equality (just this tag, no others)
        if self._value.startswith(":"):
            self._exact = True
            self._value = self._value[1:]
        else:
            self._exact = not self._value

    def eq(self, item) -> bool:
        """Return True if filter matches item."""
        tags = getattr(item, self._name) or []
        if self._exact:
            # Exact equality check
            return set(self._value) == set(tags)
        # Is given tag in list?
        return self._value in tags


class BoolFilter(FieldFilter):
    """Filter boolean values."""

    def pre_filter_eq(self):
        """Return rTorrent condition to speed up data transfer."""
        pf = prefilter_field_lookup(self._name)
        if pf is not None:
            return f'"equal={pf},value={int(self._value)}"'
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
        # Grab the function from the native operator module
        op = getattr(operator, self._op.name)
        return bool(op(float(val), float(self._value)))


def prefilter_field_lookup(name: str) -> Optional[str]:
    """Return the prefield field for a given name (if available)"""
    field = torrent.engine.field_lookup(name)
    if field is None:
        return None
    return field.prefilter_field


class FloatFilter(NumericFilterBase):
    """Filter float values."""

    FIELD_SCALE = {
        "ratio": 1000,
    }

    def pre_filter(self):
        """Prefilter a float value.

        rTorrent doesn't actually have floats, so we need to do a
        little translation for the prefiltering
        """
        pf = prefilter_field_lookup(self._name)
        if pf is None:
            return ""
        val = int(self._value) * self.FIELD_SCALE.get(self._name, 1)
        lookup_table = {
            "eq": ("equal", int(val)),
            "ge": ("greater", math.floor(val - 1)),
            "gt": ("greater", math.floor(val)),
            "le": ("less", math.ceil(val + 1)),
            "lt": ("less", math.ceil(val)),
        }
        op, val = lookup_table[self._op.name]
        return f'"{op}=value=${pf},value={val}"'

    def validate(self):
        """Validate filter condition (template method)."""
        super().validate()

        try:
            self._value = float(self._value)
        except (ValueError, TypeError) as exc:
            raise FilterError(
                f"Bad numerical value {self._value!r} in {self._condition!r} ({exc})"
            ) from exc


class TimeFilter(NumericFilterBase):
    """Filter UNIX timestamp values."""

    TIMEDELTA_UNITS = {
        "y": lambda d: d * 365 * 86400,
        "M": lambda d: d * 30 * 86400,
        "w": lambda d: d * 7 * 86400,
        "d": lambda d: d * 86400,
        "h": lambda d: d * 3600,
        "m": lambda d: d * 60,
        "s": lambda d: d,
    }
    TIMEDELTA_RE = re.compile(
        "^" + "".join(r"(?:(?P<{0}>\d+)[{0}{0}])?".format(i) for i in "yMwdhms") + "$"
    )

    def __init__(self, name: str, op: FilterOperator, value: str):
        # During validate(), one of these two must be set to something
        # non-None
        self._timestamp_offset = None
        self._timestamp = None
        super().__init__(name, op, value)

    def pre_filter(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        # A "0" might indicate just that, or possibly an empty
        # custom value.
        if self._value == 0:
            return ""
        pf = prefilter_field_lookup(self._name)
        # Add a day of wiggle room to avoid any possible timezone problems
        time_fuzz = 60 * 60 * 24
        timestamp = 0
        cmp_ = ""
        if pf is None:
            return ""
        if self._op.name in ["gt", "ge"]:
            timestamp = int(float(self._value)) - time_fuzz
            cmp_ = "greater"
        elif self._op.name in ["lt", "le"]:
            timestamp = int(float(self._value)) + time_fuzz
            cmp_ = "less"

        if timestamp and cmp_:
            return f'"{cmp_}=value=${pf},value={int(timestamp)}"'
        return ""

    def validate(self):
        # 0 is a special case
        delta = self._parse_delta()
        if delta is not None:
            self._timestamp_offset = delta
            # Invert the operators to be more intuitive, i.e. <3d
            # should match for values of less than 3 days *ago*.
            self._invert_operator()
            return
        self._timestamp = self._parse_absolute_timestamp()
        if self._timestamp is None:
            raise ValueError(f"Could not parse timestamp {self._condition!r}")

    @property
    def _value(self) -> str:
        if self._timestamp_offset is not None:
            return str(time.time() - self._timestamp_offset)
        if self._timestamp is not None:
            return str(self._timestamp)
        raise ValueError(f"Unset time value from condition {self._condition!r}")

    @_value.setter
    def _value(self, _: str) -> None:
        """Discard attempts to set the value, primarily because the
        grandparent FieldFilter tries to do it in __init__()"""
        return None

    def _invert_operator(self):
        if self._op.name == "gt":
            self._op = Operators["le"]
        elif self._op.name == "ge":
            self._op = Operators["lt"]
        elif self._op.name == "lt":
            self._op = Operators["ge"]
        elif self._op.name == "le":
            self._op = Operators["gt"]

    def _parse_delta(self) -> Optional[int]:
        match = self.TIMEDELTA_RE.match(self._condition)
        if not match:
            return None
        delta_val = 0
        for unit, val in match.groupdict().items():
            if val:
                delta_val = self.TIMEDELTA_UNITS[unit](int(val, 10))
        return delta_val

    def _parse_absolute_timestamp(self) -> Optional[int]:
        if str(self._condition).isdigit():
            # Literal UNIX timestamp
            try:
                return int(self._condition)
            except (ValueError, TypeError) as exc:
                raise FilterError(
                    f"Bad UNIX timestamp value {self._condition!r}"
                ) from exc
        # Assume it's an absolute date
        if "/" in self._condition:
            # U.S.
            dtfmt = "%m/%d/%Y"
        elif "." in self._condition:
            # European
            dtfmt = "%d.%m.%Y"
        else:
            # Fall back to ISO
            dtfmt = "%Y-%m-%d"

        val = str(self._condition).upper().replace(" ", "T")
        if "T" in val:
            # Time also given
            dtfmt += "T%H:%M:%S"[: 3 + 3 * val.count(":")]

        try:
            timestamp = time.mktime(time.strptime(val, dtfmt))
        except ValueError as exc:
            raise FilterError(
                f"Could not parse timestamp {self._condition!r} with format {dtfmt!r}"
            ) from exc
        return int(timestamp)


class TimeFilterNotNull(TimeFilter):
    """Filter UNIX timestamp values, ignore unset values unless compared to 0."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.not_null = True


class DurationFilter(TimeFilter):
    """Filter durations in seconds."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.not_null = True

    @property
    def _value(self):
        if self._condition == "0":
            return 0
        if self._timestamp_offset is not None:
            return self._timestamp_offset
        if self._timestamp is not None:
            return time.time() - self._timestamp
        raise ValueError(f"Unset time value from condition {self._condition!r}")

    @_value.setter
    def _value(self, _):
        """Discard attempts to set the value, primarily because the
        grandparent FieldFilter tries to do it in __init__()"""
        return None

    def validate(self):
        # 0 is a special case
        if self._condition == "0":
            return
        delta = self._parse_delta()
        if delta is not None:
            self._timestamp_offset = delta
            return
        self._timestamp = self._parse_absolute_timestamp()
        if self._timestamp is None:
            raise ValueError(f"Could not parse timestamp {self._condition!r}")

    def match(self, item) -> bool:
        """Return True if filter matches item."""
        if getattr(item, self._name) is None:
            # Never match "N/A" items, except when "-0" was specified
            return not bool(self._value)
        return super().match(item)

    def pre_filter(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        # A "0" might indicate just that, or possibly an empty
        # custom value.
        if self._value == 0:
            return ""
        pf = prefilter_field_lookup(self._name)
        time_fuzz = (
            60 * 60 * 24
        )  # Add a day of wiggle room to avoid any possible timezone problems
        timestamp = 0
        cmp_ = ""
        if pf is None:
            return ""
        if self._op.name in ["gt", "ge"]:
            timestamp = self._value + time_fuzz
            cmp_ = "greater"
        elif self._op.name in ["lt", "le"]:
            timestamp = self._value - time_fuzz
            cmp_ = "less"

        if timestamp and cmp_:
            return f'"{cmp_}=value=${pf},value={int(timestamp)}"'
        return ""


class ByteSizeFilter(NumericFilterBase):
    """Filter size and bandwidth values."""

    UNITS = {"b": 1, "k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}

    def pre_filter(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        comparers = {
            "gt": "greater",
            "lt": "less",
            "eq": "equal",
        }
        pf = prefilter_field_lookup(self._name)
        if pf is not None and self._op.name in comparers:
            return '"{}={},value={}"'.format(
                comparers[self._op.name],
                pf,
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
                f"Bad numerical value {self._value!r} in {self._condition!r}"
            ) from exc

        # Scale to bytes
        self._value = self._value * scale


QueryGrammar = Grammar(
    r"""
    query = (group / stmt) (ws (group / stmt))*
    stmt = (or_stmt / conds)
    or_stmt = (group / conds) (ws or ws (group / conds))*
    group = (not ws)? lpar ws stmt ws rpar
    conds = cond (ws cond)*
    cond = (&or / &lpar / &rpar / &not / named_cond / unnamed_cond)
    named_cond = word conditional filter
    unnamed_cond = filter
    filter      = (quoted_regex / quoted / glob / regex / word)
    glob = ~r"[\S]+"
    quoted_regex =  ~r'"/[^/\"]*/i?"'
    regex = ~r"/[^/]*/i?"
    quoted      = ~'"[^\"]*"'
    word        = ~r"[\w]+"
    conditional = (ne / ge / le / lt / gt / eq)
    ne          = ("!=" / "<>")
    eq          = ("==" / "=")
    gt          = (">" / "=+")
    lt          = ("<")
    ge          = (">=")
    le          = ("<=" / "=-")
    fws         = ~r"\s+"
    ws          = ~r"\s*"
    lpar = "["
    rpar = "]"
    or   = "OR"
    not  = ( "NOT" / "!" )
    """
)


class KeyNameVisitor(NodeVisitor):
    """Walk through a query tree and returns an array of key names.
    Implicit key names are not included."""

    # pylint: disable=unused-argument,missing-function-docstring
    def visit_expr(self, node, visited_children):
        output = ""
        for child in visited_children:
            output += str(child)
        return output

    def visit_named_cond(self, node, visited_children):
        return visited_children[0]

    def visit_word(self, node, visited_children):
        return [node.text]

    def visit_filter(self, node, visited_children):
        return ["name"]

    def generic_visit(self, node, visited_children):
        if visited_children:
            return [item for sublist in visited_children for item in sublist]
        return []


def create_filter(name: str, op: str, value: str):
    """Generates a filter class with the given name, operation and value"""
    field = torrent.engine.field_lookup(name)
    if field is None:
        raise SyntaxError(f"No such field '{name}'")
    filt = field._matcher
    return filt(name, op, value)


class MatcherBuilder(NodeVisitor):
    """Build a simplified tree of MatcherNodes to match an item against."""

    # pylint: disable=unused-argument,missing-function-docstring
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
        """
        real_children = [c for c in children if c is not None]
        if len(real_children) == 0:
            return None
        if len(real_children) == 1:
            return real_children[0]
        return class_(real_children)

    def visit_or_stmt(self, node, visited_children):
        children = [visited_children[0]]
        if visited_children[1] is not None:
            if isinstance(visited_children[1], list):
                for c in visited_children[1]:
                    children.append(c)
            else:
                children.append(visited_children[1])
        return OrNode(children)

    def visit_conds(self, node, visited_children):
        if len(visited_children) == 2 and isinstance(visited_children[1], list):
            children = [visited_children[0]] + visited_children[1]
        else:
            children = visited_children
        pared = self.__pare_children(children, AndNode)
        return pared

    def visit_cond(self, node, visited_children):
        if len(visited_children) == 1:
            child = visited_children[0]
            if isinstance(child, str):
                return create_filter("name", Operators["eq"], child)
            if isinstance(child, re.Pattern):
                return create_filter("name", Operators["eq"], child.pattern)
        return self.generic_visit(node, visited_children)

    def visit_query(self, node, visited_children):
        return self.__pare_children(visited_children, AndNode)

    # Unfortunate but necessary boilerplate methods

    def visit_word(self, node, visited_children):
        return node.text

    def visit_quoted(self, node, visited_children):
        return node.text[1:-1]

    def visit_glob(self, node, visited_children):
        return node.text

    def visit_regex(self, node, visited_children):
        return node.text

    def visit_quoted_regex(self, node, visited_children):
        return node.text[1:-1]

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
        return None


RE_UNQUOTED_REGEX = re.compile(r"(\w*)(!?=)(\/.*\/)")


def cli_args_to_match_str(query: Sequence) -> str:
    """Convert CLI arguments to a string. Most usefully, this will
    automatically double quote unnamed conditions or regexes if they
    have a space in them.
    """
    args = []
    for a in query:
        if " " in a and not set("=><") & set(a) and not a.startswith('"'):
            a = f'"{a}"'
        if " " in a and RE_UNQUOTED_REGEX.match(a):
            a = RE_UNQUOTED_REGEX.sub(r'\1\2"\3"', a)
        args.append(a)
    return " ".join(args)


def create_matcher(query: Union[str, Sequence[str]]):
    """Utility function to build a matcher from a query string."""
    if not isinstance(query, str):
        query_str = cli_args_to_match_str(query)
    else:
        query_str = query
    return MatcherBuilder().visit(QueryGrammar.parse(query_str))
