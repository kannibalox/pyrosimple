""" Torrent Item Filters.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import fnmatch
import operator
import re
import time

from dataclasses import dataclass
from typing import Any, Callable, List

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


def truth(val, context="statement") -> bool:
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
        if int(config.settings.get("FAST_QUERY")) == 1:
            return ""
        if len(self.children) == 1:
            return str(self.children[0].pre_filter())
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

    CLEAN_PRE_VAL_RE = re.compile(r"(?:\[.*?]\])|(?:\(.*?]\))|(?:{.*?]})|(?:\\)")
    SPLIT_PRE_VAL_RE = re.compile(r"[^a-zA-Z0-9/_]+")
    SPLIT_PRE_GLOB_RE = re.compile(r"[?*]+")

    def validate(self):
        """Validate filter condition (template method)."""

        super().validate()
        self._value: str = self._value
        self._template = None
        self._flags = 0
        self._matcher: Callable[Any, Any]
        if self._value == '""':
            self._matcher = lambda val, _: val == ""
        elif self._value.startswith("/") and (
            self._value.endswith("/") or self._value.endswith("/i")
        ):
            if self._value in ["//", "/.*/", "//i", "/.*/i"]:
                self._matcher = lambda _, __: True
            else:
                value = self._value
                if self._value.endswith("/i"):
                    self._flags = re.IGNORECASE
                    value = self._value.rstrip("i")
                regex = re.compile(value[1:-1], self._flags)
                self._matcher = lambda val, _: regex.search(val)
        elif self._value.startswith("{{") or self._value.endswith("}}"):

            def _template_globber(val, item):
                """Helper method to allow templating a glob."""
                pattern = torrent.rtorrent.format_item(
                    torrent.rtorrent.env.from_string(self._template), item
                )
                return fnmatch.fnmatchcase(val, pattern)

            self._template = self._value
            self._matcher = _template_globber
        else:
            self._matcher = lambda val, _: fnmatch.fnmatchcase(val, self._value)

    def pre_filter_eq(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        pf = torrent.engine.FieldDefinition.lookup(self._name).prefilter_field
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
        else:
            needle = self.CLEAN_PRE_VAL_RE.sub(" ", self._value)
            split_needle = self.SPLIT_PRE_GLOB_RE.split(needle)
        needle = list(sorted(split_needle, key=len))[-1]

        if needle:
            try:
                needle.encode("ascii")
            except UnicodeEncodeError:
                return ""
            needle = needle.replace('"', r"\\\"")
            return r'"string.contains_i=${},\"{}\""'.format(pf, needle)

        return ""

    def eq(self, item):
        """Return True if filter matches item."""
        val = getattr(item, self._name) or ""
        result = self._matcher(val, item)
        return result


class FilesFilter(PatternFilter):
    """Pattern filter on filenames in a torrent."""

    def match(self, item) -> bool:
        """Return True if filter matches item."""
        val = getattr(item, self._name)
        if val is not None:
            for fileinfo in val:
                if fnmatch.fnmatchcase(fileinfo.path, self._value):
                    return True
            return False
        return False


class TaggedAsFilter(FieldFilter):
    """Case-insensitive tags filter. Tag fields are white-space separated lists
    of tags.
    """

    def pre_filter(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        pf = torrent.engine.FieldDefinition.lookup(self._name).prefilter_field
        if pf is not None:
            if not self._value:
                return f'"not=${pf}"'
            val = self._value
            if self._exact:
                val = val.split().pop()
            return r'"string.contains_i=${},\"{}\""'.format(
                pf, val.replace('"', r"\\\"")
            )
        return ""

    def validate(self):
        """Validate filter condition (template method)."""
        super().validate()
        self._value = self._value.lower()

        # If the tag starts with '=', test on equality (just this tag, no others)
        if self._value.startswith(":"):
            self._exact = True
            self._value = self._value[1:]
        else:
            self._exact = not self._value

        # For exact matches, value is the set to compare to
        if self._exact:
            # Empty tag means empty set, not set of one empty string
            self._value = {self._value} if self._value else set()

    def match(self, item) -> bool:
        """Return True if filter matches item."""
        tags = getattr(item, self._name) or []
        if self._exact:
            # Equality check
            return self._value == set(tags)
        # Is given tag in list?
        return self._value in tags


class BoolFilter(FieldFilter):
    """Filter boolean values."""

    def pre_filter_eq(self):
        """Return rTorrent condition to speed up data transfer."""
        pf = torrent.engine.FieldDefinition.lookup(self._name).prefilter_field
        if pf is not None:
            return '"equal={},value={}"'.format(pf, int(self._value))
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
        return bool(op(float(val), self._value))


class FloatFilter(NumericFilterBase):
    """Filter float values."""

    FIELD_SCALE = dict(
        ratio=1000,
    )

    # pylint: disable=missing-function-docstring
    def pre_filter_eq(self):
        pf = torrent.engine.FieldDefinition.lookup(self._name).prefilter_field
        if pf is not None:
            val = int(self._value * self.FIELD_SCALE.get(self._name, 1))
            return f'"equal=value=${pf},value={val}"'
        return ""

    def pre_filter_ge(self):
        pf = torrent.engine.FieldDefinition.lookup(self._name).prefilter_field
        if pf is not None:
            val = int(self._value * self.FIELD_SCALE.get(self._name, 1))
            return f'"greater=value=${pf},value={val-1}"'
        return ""

    def pre_filter_gt(self):
        pf = torrent.engine.FieldDefinition.lookup(self._name).prefilter_field
        if pf is not None:
            val = int(self._value * self.FIELD_SCALE.get(self._name, 1))
            return f'"greater=value=${pf},value={val}"'
        return ""

    def pre_filter_le(self):
        pf = torrent.engine.FieldDefinition.lookup(self._name).prefilter_field
        if pf is not None:
            val = int(self._value * self.FIELD_SCALE.get(self._name, 1))
            return f'"less=value=${pf},value={val+1}"'
        return ""

    def pre_filter_lt(self):
        pf = torrent.engine.FieldDefinition.lookup(self._name).prefilter_field
        if pf is not None:
            val = int(self._value * self.FIELD_SCALE.get(self._name, 1))
            return f'"less=value=${pf},value={val}"'
        return ""

    # pylint: enable=missing-function-docstring

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
        "^" + "".join(r"(?:(?P<{0}>\d+)[{0}{0}])?".format(i) for i in "yMwdhms") + "$"
    )

    def pre_filter(self) -> str:
        """Return rTorrent condition to speed up data transfer."""
        pf = torrent.engine.FieldDefinition.lookup(self._name).prefilter_field
        if pf is not None:
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

            return '"{}=value=${},value={}"'.format(cmp_, pf, int(timestamp))
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
                    f"Bad timestamp value {self._value!r} in {self._condition!r}"
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
                # Invert the value for more intuitive matching (in line with original code too)
                # e.g. 'completed<1d' should return things completed less than one day *ago*
                else:
                    if self._op.name == "gt":
                        self._op = Operators["le"]
                    elif self._op.name == "ge":
                        self._op = Operators["lt"]
                    elif self._op.name == "lt":
                        self._op = Operators["ge"]
                    elif self._op.name == "le":
                        self._op = Operators["gt"]
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
                        f"Bad timestamp value {self._value!r} in {self._condition!r} ({exc})"
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
        pf = torrent.engine.FieldDefinition.lookup(self._name).prefilter_field
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
    query = (group / stmt)+
    stmt = (or_stmt / conds)
    or_stmt = (group / conds) ws or ws (group / conds)
    group = (not ws)? lpar ws stmt ws rpar
    conds = cond (ws cond)*
    cond = (&or / &lpar / &rpar / &not / named_cond / unnamed_cond)
    named_cond = word conditional filter
    unnamed_cond = filter
    filter      = (quoted / glob / regex / word)
    glob = ~r"[\S]+"
    regex = ~"/[^/]*/i?"
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
        return []


def create_filter(name: str, op: str, value: str):
    """Generates a filter class with the given name, operation and value"""
    field = torrent.engine.FieldDefinition.lookup(name)
    if field is None:
        raise SyntaxError(f"No such field '{name}'")
    filt = field._matcher
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
        """
        real_children = [c for c in children if c is not None]
        if len(real_children) == 0:
            return None
        if len(real_children) == 1:
            return real_children[0]
        return class_(real_children)

    def visit_or_stmt(self, node, visited_children):
        return OrNode([c for c in visited_children if c is not None])

    def visit_conds(self, node, visited_children):
        if len(visited_children) == 2 and isinstance(visited_children[1], list):
            children = [visited_children[0]] + visited_children[1]
        else:
            children = visited_children
        pared = self.__pare_children(children, AndNode)
        return pared

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
        return None


def create_matcher(query: str):
    """Utility function to build a matcher from a query string."""
    return MatcherBuilder().visit(QueryGrammar.parse(query))
