""" Torrent Engine Interface.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""

import logging
import os
import re
import time
import warnings

from typing import Callable, Dict, Optional, Set, cast

from pyrosimple import config, error
from pyrosimple.util import fmt, matching, metafile, rpc, traits


logger = logging.getLogger(__name__)


def untyped(val):
    """A type specifier for fields that does nothing."""
    return val


def ratio_float(intval: float) -> float:
    """Convert scaled integer ratio to a normalized float."""
    return intval / 1000.0


def percent(floatval: float) -> float:
    """Convert float ratio to a percent value."""
    return floatval * 100.0


def _duration(start: Optional[float], end: Optional[float]) -> Optional[float]:
    """Return time delta."""
    if start is None:
        start = 0.0
    if end is None:
        end = 0.0
    if start and end:
        if start > end:
            return None
        return end - start
    if start:
        return time.time() - start
    return None


def _interval_split(
    interval: str, only: Optional[str] = None, event_re=re.compile("[A-Z][0-9]+")
):
    """Split C{interval} into a series of event type and timestamp tuples.
    An exaple of the input is "R1283008245P1283008268".
    Returns events in reversed order (latest first).
    """

    def split_event(event):
        "Helper to parse events."
        kind, val = event[:1], event[1:]
        try:
            return kind, float(val)
        except (TypeError, ValueError):
            return None, 0

    return list(
        reversed(
            [
                split_event(i)
                for i in event_re.findall(interval)
                if not only or i.startswith(only)
            ]
        )
    )


def _interval_sum(
    interval: str, start: Optional[float] = None, end: Optional[float] = None
) -> Optional[int]:
    """Return sum of intervals between "R"esume and "P"aused events
    in C{interval}, optionally limited by a time window defined
    by C{start} and C{end}. Return ``None`` if there's no sensible
    information.

    C{interval} is a series of event types and timestamps,
    e.g. "R1283008245P1283008268".
    """
    end = float(end) if end else time.time()
    events = _interval_split(interval)
    result = []

    while events:
        event, resumed = events.pop()

        if event != "R":
            # Ignore other events
            continue
        resumed = max(resumed, start or resumed)

        if events:  # Further events?
            if not events[-1][0] == "P":
                continue  # If not followed by "P", it's not a valid interval
            _, paused = events.pop()
            paused = min(paused, end)
        else:
            # Currently active, ends at time window
            paused = end

        if resumed >= paused:
            # Ignore empty intervals
            continue

        result.append(paused - resumed)

    return sum(result) if result else None


def _fmt_duration(duration):
    """Format duration value."""
    return fmt.human_duration(duration, 0, 2, True)


def _fmt_tags(tagset: Set[str]) -> str:
    """Convert set of strings to sorted space-separated list as a string."""
    return " ".join(sorted(tagset))


def _fmt_files(filelist) -> str:
    """Produce a file listing."""
    depth = max(i.path.count("/") for i in filelist)
    pad = ["\uFFFE"] * depth

    base_indent = " " * 38
    indent = 0
    result = []
    prev_path = pad
    sorted_files = sorted(
        (i.path.split("/")[:-1] + pad, i.path.rsplit("/", 1)[-1], i) for i in filelist
    )

    for path, name, fileinfo in sorted_files:
        path = path[:depth]
        if path != prev_path:
            common = min(
                [depth]
                + [
                    idx
                    for idx, (dirname, prev_name) in enumerate(zip(path, prev_path))
                    if dirname != prev_name
                ]
            )
            while indent > common:
                indent -= 1
                result.append(f"{base_indent}{' ' * indent}/")

            for dirname in path[common:]:
                if dirname == "\uFFFE":
                    break
                result.append(f"{base_indent}{' ' * indent}\\ {dirname}")
                indent += 1

        prio = {0: "off ", 1: "    ", 2: "high"}.get(fileinfo.prio, "????")
        result.append(
            f"  {prio} {fmt.iso_datetime(fileinfo.mtime)} {fmt.human_size(fileinfo.size)} {' ' * indent}| {name}"
        )

        prev_path = path

    while indent > 0:
        indent -= 1
        result.append(f"{base_indent}{' ' * indent}/")
    result.append(f"{base_indent}= {len(filelist)} file(s)")

    return "\n".join(result)


def detect_traits(item):
    """Build traits list from attributes of the passed item. Currently,
    "kind_51", "name" and "alias" are considered.

    See pyrosimple.util.traits:dectect_traits for more details.
    """
    return traits.detect_traits(
        name=item.name,
        alias=item.alias,
        filetype=(list(item.fetch("kind_51")) or [None]).pop(),
    )


class FieldDefinition:
    """Download item field."""

    CONSTANT_FIELDS = {"hash"}

    def __init__(
        self,
        valtype,
        name: str,
        doc: str,
        accessor=None,
        matcher=None,
        formatter=None,
        requires=None,
        prefilter_field=None,
    ):
        self.valtype = valtype
        self.name = name
        self.__doc__ = doc
        self.requires = requires or []
        self._accessor = accessor
        self._matcher = matcher
        self.formatter = formatter
        self.prefilter_field: Optional[str] = prefilter_field
        if accessor is None:
            self._accessor = lambda o: o.rpc_call("d." + name)
            if requires is None:
                self.requires = ["d." + name]

        if name in FIELD_REGISTRY:
            raise RuntimeError("INTERNAL ERROR: Duplicate field definition")
        FIELD_REGISTRY[name] = self

    def __repr__(self):
        """Return a representation of internal state."""
        return f"<{self.__class__.__name__}({self.valtype!r}, {self.name!r}, {self.__doc__!r})>"

    def __get__(self, obj, cls=None):
        if obj is None:
            return self
        return self.valtype(
            self._accessor(obj) if self._accessor else obj._fields[self.name]
        )

    def __delete__(self, obj):
        raise RuntimeError(f"Can't delete field {self.name!r}")


class ImmutableField(FieldDefinition):
    """Read-only download item field."""

    def __set__(self, obj, val):
        raise RuntimeError(f"Immutable field {self.name!r}")


class ConstantField(ImmutableField):
    """Read-only download item field with constant value."""

    # This can be cached


class DynamicField(ImmutableField):
    """Read-only download item field with dynamic value."""

    # This cannot be cached


class OnDemandField(DynamicField):
    """Only exists for backwards compatiblity."""


class MutableField(FieldDefinition):
    """Writable download item field"""

    def __init__(
        self,
        valtype,
        name,
        doc,
        accessor=None,
        matcher=None,
        formatter=None,
        requires=None,
        prefilter_field=None,
        setter: Callable = None,
    ):
        super().__init__(
            valtype, name, doc, accessor, matcher, formatter, requires, prefilter_field
        )
        self._setter = setter

    def __set__(self, obj, val, cls=None):
        if self._setter is None:
            raise NotImplementedError
        self._setter(obj, val)


FIELD_REGISTRY: Dict[str, FieldDefinition] = {}
FIELD_GENERATOR_REGISTRY: Dict[str, Callable] = {}


def field_lookup(name: str) -> Optional[FieldDefinition]:
    """Try to find field C{name}.

    @return: Field descriptions, see C{matching.ConditionParser} for details.
    """
    if name not in FIELD_REGISTRY:
        TorrentProxy.add_manifold_attribute(name)
    try:
        return FIELD_REGISTRY[name]
    except KeyError:
        return None


def core_fields():
    """Generate built-in field definitions"""
    yield ConstantField(
        bool,
        "is_private",
        "private flag set (no DHT/PEX)?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "PRV" if val else "PUB",
        requires=["d.is_private"],
        prefilter_field="d.is_private=",
    )
    # Classification
    yield DynamicField(
        set,
        "tagged",
        "has certain tags? (not related to the 'tagged' view)",
        matcher=matching.TaggedAsFilter,
        accessor=lambda o: set(o.rpc_call("d.custom", ["tags"]).lower().split()),
        formatter=_fmt_tags,
        requires=["d.custom=tags"],
        prefilter_field="d.custom=tags",
    )
    yield DynamicField(
        set,
        "views",
        "views this item is attached to",
        matcher=matching.TaggedAsFilter,
        formatter=_fmt_tags,
        requires=["d.views"],
        prefilter_field="d.views=",
    )
    yield DynamicField(
        set,
        "kind",
        "ALL kinds of files in this item (the same as kind_0)",
        matcher=matching.TaggedAsFilter,
        formatter=_fmt_tags,
        accessor=lambda o: o.fetch("kind_0"),
    )
    yield DynamicField(
        list,
        "traits",
        "automatic classification of this item (audio, video, tv, movie, etc.)",
        matcher=matching.TaggedAsFilter,
        formatter=lambda v: "/".join(v or ["misc", "other"]),
        accessor=detect_traits,
    )

    # Basic fields
    yield ConstantField(
        str,
        "name",
        "name (file or root directory)",
        matcher=matching.PatternFilter,
        prefilter_field="d.name=",
    )
    yield ConstantField(
        int,
        "size",
        "data size",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: o.rpc_call("d.size_bytes"),
        requires=["d.size_bytes"],
        prefilter_field="d.size_bytes=",
    )
    yield MutableField(
        int,
        "prio",
        "priority (0=off, 1=low, 2=normal, 3=high)",
        matcher=matching.FloatFilter,
        accessor=lambda o: o.rpc_call("d.priority"),
        requires=["d.priority"],
        formatter=lambda val: "X- +"[val],
        prefilter_field="d.priority=",
    )
    yield ConstantField(
        str,
        "tracker",
        "first in the list of announce URLs",
        matcher=matching.PatternFilter,
        accessor=lambda o: (o.announce_urls(default=[None]) or [None])[0],
        requires=["t.multicall=,t.url=,t.is_enabled="],
    )

    def _alias_accessor(o):
        """Check the memoized alias custom field
        If it's defined as a key in the config, just return it
        Otherwise, check if it can be reduced down further.
        The worst case is that it doesn't exist to begin with,
        and then the tracker field needs to be referenced to figure it
        out properly.
        """
        memoized_alias = o.rpc_call("d.custom", ["memo_alias"])
        if memoized_alias in config.settings["ALIASES"]:
            return memoized_alias
        if memoized_alias:
            new_alias = config.map_announce2alias(memoized_alias)
            if new_alias:
                o.rpc_call("d.custom.set", ["memo_alias", new_alias])
            else:
                return memoized_alias
        else:
            new_alias = config.map_announce2alias(o.tracker)

        if memoized_alias != new_alias:
            o.rpc_call("d.custom.set", ["memo_alias", new_alias])
        return new_alias

    yield ConstantField(
        str,
        "alias",
        "tracker alias or domain",
        matcher=matching.PatternFilter,
        accessor=_alias_accessor,
        requires=["d.custom=memo_alias"],
    )
    yield DynamicField(
        str,
        "message",
        "current tracker message",
        matcher=matching.PatternFilter,
        requires=["d.message"],
        prefilter_field="d.message=",
    )

    # State
    yield DynamicField(
        bool,
        "is_open",
        "download open?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "OPN" if val else "CLS",
        requires=["d.is_open"],
        prefilter_field="d.is_open=",
    )
    yield DynamicField(
        bool,
        "is_active",
        "download active?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "ACT" if val else "STP",
        requires=["d.is_active"],
        prefilter_field="d.is_active=",
    )
    yield DynamicField(
        bool,
        "is_complete",
        "download complete?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "DONE" if val else "PART",
        accessor=lambda o: o.rpc_call("d.complete"),
        requires=["d.complete"],
        prefilter_field="d.complete=",
    )
    yield ConstantField(
        bool,
        "is_multi_file",
        "single- or multi-file download?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "DIR " if val else "FILE",
        prefilter_field="d.is_multi_file=",
    )
    yield MutableField(
        bool,
        "is_ignored",
        "ignore commands?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "IGN!" if int(val) else "HEED",
        accessor=lambda o: o.rpc_call("d.ignore_commands"),
        requires=["d.ignore_commands"],
        prefilter_field="d.ignore_commands=",
        setter=lambda o, val: o.ignore(int(val)),
    )
    yield DynamicField(
        bool,
        "is_ghost",
        "has no data file or directory?",
        matcher=matching.BoolFilter,
        accessor=lambda o: not os.path.exists(o.datapath()) if o.datapath() else None,
        formatter=lambda val: "GHST" if val else "DATA",
        requires=["d.directory", "d.is_multi_file"],
    )

    # Paths
    yield DynamicField(
        str,
        "directory",
        "directory containing download data",
        matcher=matching.PatternFilter,
        prefilter_field="d.directory=",
    )
    yield DynamicField(
        str,
        "path",
        "path to download data",
        matcher=matching.PatternFilter,
        accessor=lambda o: o.datapath(),
        requires=["d.directory", "d.is_multi_file"],
    )
    yield DynamicField(
        str,
        "realpath",
        "real path to download data",
        matcher=matching.PatternFilter,
        accessor=lambda o: os.path.realpath(o.datapath()),
        requires=["d.directory", "d.is_multi_file"],
    )
    yield ConstantField(
        str,
        "metafile",
        "path to torrent file",
        matcher=matching.PatternFilter,
        accessor=lambda o: os.path.expanduser(str(o.rpc_call("d.tied_to_file"))),
        requires=["d.tied_to_fiel"],
    )
    yield ConstantField(
        str,
        "sessionfile",
        "path to session file",
        matcher=matching.PatternFilter,
        accessor=lambda o: os.path.expanduser(str(o.rpc_call("d.session_file"))),
        requires=["d.session_file"],
        prefilter_field="d.session_file=",
    )
    yield ConstantField(
        list,
        "files",
        "list of files in this item",
        matcher=matching.FilesFilter,
        formatter=_fmt_files,
        accessor=lambda o: o._get_files(),
    )
    yield ConstantField(
        int,
        "fno",
        "number of files in this item",
        matcher=matching.FloatFilter,
        accessor=lambda o: o.rpc_call("d.size_files"),
        requires=["d.size_files"],
    )

    # Bandwidth & Data Transfer
    yield DynamicField(
        percent,
        "done",
        "completion in percent",
        matcher=matching.FloatFilter,
        accessor=lambda o: float(o.rpc_call("d.completed_bytes"))
        / o.rpc_call("d.size_bytes"),
        requires=["d.size_bytes", "d.completed_bytes"],
    )
    yield DynamicField(
        ratio_float,
        "ratio",
        "normalized ratio (1:1 = 1.0)",
        matcher=matching.FloatFilter,
        accessor=lambda o: o.rpc_call("d.ratio"),
        requires=["d.ratio"],
        prefilter_field="d.ratio=",
    )
    yield DynamicField(
        int,
        "uploaded",
        "amount of uploaded data",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: o.rpc_call("d.up.total"),
        requires=["d.up.total"],
        prefilter_field="d.up.total=",
    )
    yield DynamicField(
        int,
        "xfer",
        "transfer rate",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: o.fetch("up") + o.fetch("down"),
        requires=["d.up.rate", "d.down.rate"],
    )

    def _last_xfer_accessor(o):
        engine = o._engine
        if config.settings.SAFETY_CHECKS_ENABLED and not engine.has_method(
            "d.timestamp.last_xfer"
        ):
            warnings.warn(
                "Method 'd.timestamp.last_xfer' does not exist! See https://kannibalox.github.io/pyrosimple/rtorrent-config/ for information on setting up rtorrent.rc.",
                stacklevel=2,
            )
            return 0
        else:
            return int(o.rpc_call("d.timestamp.last_xfer") or 0)

    yield DynamicField(
        int,
        "last_xfer",
        "last time data was transferred",
        matcher=matching.TimeFilter,
        accessor=_last_xfer_accessor,
        formatter=fmt.iso_datetime_optional,
    )
    yield DynamicField(
        int,
        "down",
        "download rate",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: o.rpc_call("d.down.rate"),
        requires=["d.down.rate"],
        prefilter_field="d.down.rate=",
    )
    yield DynamicField(
        int,
        "up",
        "upload rate",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: o.rpc_call("d.up.rate"),
        requires=["d.up.rate"],
        prefilter_field="d.up.rate=",
    )
    yield DynamicField(
        str,
        "throttle",
        "throttle group name (NULL=unlimited, NONE=global)",
        matcher=matching.PatternFilter,
        accessor=lambda o: o.rpc_call("d.throttle_name"),
        formatter=lambda v: v if v else "NONE",
        requires=["d.throttle_name"],
        prefilter_field="d.throttle_name=",
    )

    # Lifecyle
    yield DynamicField(
        int,
        "loaded",
        "time metafile was loaded",
        matcher=matching.TimeFilterNotNull,
        accessor=lambda o: int(o.rpc_call("d.custom", ["tm_loaded"]) or "0", 10),
        formatter=fmt.iso_datetime_optional,
        requires=["d.custom=tm_loaded"],
        prefilter_field="d.custom=tm_loaded",
    )
    yield DynamicField(
        int,
        "started",
        "time download was FIRST started",
        matcher=matching.TimeFilterNotNull,
        accessor=lambda o: int(o.rpc_call("d.custom", ["tm_started"]) or "0", 10),
        formatter=fmt.iso_datetime_optional,
        requires=["d.custom=tm_started"],
        prefilter_field="d.custom=tm_loaded",
    )

    def _leechtime_accessor(o):
        leechtime = _interval_sum(
            o.rpc_call("d.custom", ["activations"]), end=o.completed
        )
        if not leechtime:
            leechtime = _duration(o.started, o.completed)
        return leechtime

    yield DynamicField(
        untyped,
        "leechtime",
        "time taken from start to completion",
        matcher=matching.DurationFilter,
        accessor=_leechtime_accessor,
        formatter=_fmt_duration,
        requires=[
            "d.custom=tm_completed",
            "d.custom=tm_started",
            "d.custom=activations",
        ],
    )
    yield DynamicField(
        int,
        "completed",
        "time download was finished",
        matcher=matching.TimeFilterNotNull,
        accessor=lambda o: int(o.rpc_call("d.custom", ["tm_completed"]) or "0", 10),
        formatter=fmt.iso_datetime_optional,
        requires=["d.custom=tm_completed"],
        prefilter_field="d.custom=tm_completed",
    )
    yield DynamicField(
        untyped,
        "seedtime",
        "total seeding time after completion",
        matcher=matching.DurationFilter,
        accessor=lambda o: _interval_sum(
            o.rpc_call("d.custom", ["activations"]), start=o.completed
        )
        if o.rpc_call("d.complete")
        else None,
        formatter=_fmt_duration,
        requires=["d.custom=tm_completed", "d.complete", "d.custom=activations"],
    )

    def _last_active_accessor(o):
        engine = o._engine
        if config.settings.SAFETY_CHECKS_ENABLED and not engine.has_method(
            "d.timestamp.last_active"
        ):
            warnings.warn(
                "Method 'd.timestamp.last_active' does not exist! See https://kannibalox.github.io/pyrosimple/rtorrent-config/ for information on setting up rtorrent.rc.",
                stacklevel=2,
            )
            return 0
        else:
            return int(o.rpc_call("d.timestamp.last_active") or 0)

    yield DynamicField(
        int,
        "active",
        "last time a peer was connected",
        matcher=matching.TimeFilter,
        accessor=_last_active_accessor,
        formatter=fmt.iso_datetime_optional,
        requires=["d.timestamp.last_active"],
    )
    yield DynamicField(
        int,
        "stopped",
        "time download was last stopped or paused",
        matcher=matching.TimeFilterNotNull,
        accessor=lambda o: (
            _interval_split(o.rpc_call("d.custom", ["activations"]), only="P")
            + [(0, 0)]
        )[0][1],
        formatter=fmt.iso_datetime_optional,
        requires=["d.custom=activations"],
    )


def generate_custom_field(name: str) -> FieldDefinition:
    """Create fields from custom keys"""
    custom_name = name.split("_", 1)[1]
    accessor = lambda o: o.rpc_call("d.custom", [custom_name])
    description = f"custom attribute {custom_name}"
    requires = [f"d.custom={custom_name}"]
    # Handle custom1, custom2, etc as a special case
    if len(custom_name) == 1 and custom_name in "12345":
        accessor = lambda o: o.rpc_call(f"d.custom{custom_name}")
        description = f"custom{custom_name}"
        requires = [f"d.custom{custom_name}"]
    return DynamicField(
        str,
        name,
        description,
        matcher=matching.PatternFilter,
        accessor=accessor,
        requires=requires,
    )


def generate_kind_field(name: str) -> FieldDefinition:
    """Generate kind percentile fields"""
    limit = int(name[5:].lstrip("0") or "0", 10)
    if limit > 100:
        raise error.UserError(f"kind_N: N can't be greater than 100 in {name!r}")
    return DynamicField(
        set,
        name,
        f"kinds of files that make up more than {limit}% of this item's size",
        accessor=lambda o: o._get_kind(limit),
        matcher=matching.TaggedAsFilter,
        formatter=_fmt_tags,
        requires=["d.custom=kind"],
    )


def generate_guessit_field(name: str) -> Optional[FieldDefinition]:
    """Create fields based on the guessit parser (if installed)."""
    try:
        import guessit  # pylint: disable=import-outside-toplevel
    except ModuleNotFoundError:
        logger.error(
            "'guessit' module not found while loading field '%s', install with: pip install guessit",
            name,
        )
        return None

    guess_field = name[8:]

    def _guess_accessor(o):
        return guessit.guessit(o.rpc_call("d.name")).get(guess_field, "")

    return DynamicField(
        str,
        name,
        f"Guessit field {guess_field}",
        accessor=_guess_accessor,
        requires=["d.name"],
    )


class TorrentProxy:
    """A single download item."""

    @classmethod
    def add_manifold_attribute(cls, name) -> Optional[FieldDefinition]:
        """Register a manifold engine attribute.

        @return: field definition object, or None if "name" isn't a manifold attribute.
        """
        if name in FIELD_REGISTRY:
            return FIELD_REGISTRY[name]
        for prefix, generator in FIELD_GENERATOR_REGISTRY.items():
            if name.startswith(prefix):
                field = generator(name)
                if field is not None:
                    setattr(cls, name, field)
                    FIELD_REGISTRY[name] = field
                    return cast(FieldDefinition, field)
                else:
                    return None
        return None

    @classmethod
    def add_field_generator(cls, prefix: str, generator: Callable):
        """Add a field generator with a given prefix to the registry"""
        FIELD_GENERATOR_REGISTRY[prefix] = generator

    @classmethod
    def add_field(cls, field):
        """Add a custom field to the class"""
        setattr(cls, field.name, field)
        FIELD_REGISTRY[field.name] = field
        if isinstance(field, ConstantField):
            FieldDefinition.CONSTANT_FIELDS.add(field.name)

    @classmethod
    def add_core_fields(cls, *_, **__):
        """Add any custom fields defined in the configuration."""
        for field in core_fields():
            cls.add_field(field)
        for prefix, generator in {
            "custom_": generate_custom_field,
            "kind_": generate_kind_field,
            "guessit_": generate_guessit_field,
        }.items():
            cls.add_field_generator(prefix, generator)

    def __init__(self):
        """Initialize object."""
        self._fields = {}

    def __hash__(self):
        """Make item hashable for Python."""
        return self.hash

    def __eq__(self, other):
        """Compare items based on their infohash."""
        return other and self.hash == getattr(other, "hash", None)

    hash = ConstantField(
        str,
        "hash",
        "info hash",
        matcher=matching.PatternFilter,
        prefilter_field="d.hash=",
    )

    def __repr__(self):
        """Return a representation of internal state."""

        def mask(key, val):
            "helper to hide sensitive stuff"
            if key in ("tracker", "custom_memo_alias"):
                return key, metafile.mask_keys(val)
            return key, val

        return "<{}({})>".format(
            self.__class__.__name__,
            ", ".join(sorted("%s=%r" % mask(k, v) for k, v in self._fields.items())),
        )


TorrentProxy.add_core_fields()


class TorrentView:
    """A view on a subset of torrent items."""

    def __init__(self, engine, viewname, matcher=None):
        """Initialize view on torrent items."""
        self.engine = engine
        self.viewname = viewname or "default"
        self.matcher = matcher
        self._items = None

    def __iter__(self):
        return self.items()

    def _fetch_items(self):
        """Fetch to attribute."""
        if self._items is None:
            self._items = list(self.engine.items(self))

        return self._items

    def _check_hash_view(self) -> Optional[str]:
        """Return infohash if view name refers to a single item, else None."""
        infohash = None
        if self.viewname.startswith("#"):
            infohash = self.viewname[1:]
        elif len(self.viewname) == 40:
            try:
                int(self.viewname, 16)
            except (TypeError, ValueError):
                pass
            else:
                infohash = str(self.viewname)
        return infohash

    def size(self) -> int:
        """Total unfiltered size of view."""
        if self._check_hash_view():
            return 1
        return int(self.engine.open().view.size(rpc.NOHASH, self.viewname))

    def items(self):
        """Get list of download items."""
        if self.matcher:
            for item in self._fetch_items():
                if self.matcher.match(item):
                    yield item
        else:
            for item in self._fetch_items():
                yield item
