""" Torrent Engine Interface.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import os
import re
import time

from typing import Any, Callable, Dict, Optional, Set

from pyrosimple import config, error
from pyrosimple.util import fmt, matching, metafile, rpc, traits


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


def _interval_split(interval, only=None, event_re=re.compile("[A-Z][0-9]+")):
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

    if hasattr(interval, "fetch"):
        interval = interval.fetch("custom_activations")

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


def _fmt_files(filelist):
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

        result.append(
            "  %s %s %s %s| %s"
            % (
                {0: "off ", 1: "    ", 2: "high"}.get(fileinfo.prio, "????"),
                fmt.iso_datetime(fileinfo.mtime),
                fmt.human_size(fileinfo.size),
                " " * indent,
                name,
            )
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

    FIELDS: Dict[str, Any] = {}
    CONSTANT_FIELDS = {"hash"}

    @classmethod
    def lookup(cls, name):
        """Try to find field C{name}.

        @return: Field descriptions, see C{matching.ConditionParser} for details.
        """
        try:
            field = cls.FIELDS[name]
        except KeyError:
            # Is it a custom attribute?
            field = TorrentProxy.add_manifold_attribute(name)

        return field if field else None

    def __init__(
        self,
        valtype,
        name: str,
        doc: str,
        accessor=None,
        matcher=None,
        formatter=None,
        requires=None,
    ):
        self.valtype = valtype
        self.name = name
        self.__doc__ = doc
        self.requires = requires or []
        self._accessor = accessor
        self._matcher = matcher
        self.formatter = formatter
        if accessor is None:
            self._accessor = lambda o: o.rpc_call("d." + name)
            if requires is None:
                self.requires = ["d." + name]

        if name in FieldDefinition.FIELDS:
            raise RuntimeError("INTERNAL ERROR: Duplicate field definition")
        FieldDefinition.FIELDS[name] = self

    def __repr__(self):
        """Return a representation of internal state."""
        return "<{}({!r}, {!r}, {!r})>".format(
            self.__class__.__name__,
            self.valtype,
            self.name,
            self.__doc__,
        )

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
        setter: Callable = None,
    ):
        super().__init__(valtype, name, doc, accessor, matcher, formatter, requires)
        self._setter = setter

    def __set__(self, obj, val, cls=None):
        if self._setter is None:
            raise NotImplementedError
        self._setter(obj, val)


def core_fields():
    """Generate built-in field definitions"""
    yield ConstantField(
        bool,
        "is_private",
        "private flag set (no DHT/PEX)?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "PRV" if val else "PUB",
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
    )
    yield DynamicField(
        set,
        "views",
        "views this item is attached to",
        matcher=matching.TaggedAsFilter,
        formatter=_fmt_tags,
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
        str, "name", "name (file or root directory)", matcher=matching.PatternFilter
    )
    yield ConstantField(
        int,
        "size",
        "data size",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: o.rpc_call("d.size_bytes"),
        requires=["d.size_bytes"],
    )
    yield MutableField(
        int,
        "prio",
        "priority (0=off, 1=low, 2=normal, 3=high)",
        matcher=matching.FloatFilter,
        accessor=lambda o: o.rpc_call("d.priority"),
        requires=["d.priority"],
        formatter=lambda val: "X- +"[val],
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
        str, "message", "current tracker message", matcher=matching.PatternFilter
    )

    # State
    yield DynamicField(
        bool,
        "is_open",
        "download open?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "OPN" if val else "CLS",
    )
    yield DynamicField(
        bool,
        "is_active",
        "download active?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "ACT" if val else "STP",
    )
    yield DynamicField(
        bool,
        "is_complete",
        "download complete?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "DONE" if val else "PART",
        accessor=lambda o: o.rpc_call("d.complete"),
        requires=["d.complete"],
    )
    yield ConstantField(
        bool,
        "is_multi_file",
        "single- or multi-file download?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "DIR " if val else "FILE",
    )
    yield MutableField(
        bool,
        "is_ignored",
        "ignore commands?",
        matcher=matching.BoolFilter,
        formatter=lambda val: "IGN!" if int(val) else "HEED",
        accessor=lambda o: o.rpc_call("d.ignore_commands"),
        requires=["d.ignore_commands"],
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
        accessor=lambda o: os.path.expanduser(str(o.rpc_call("d.session_file"))),
        requires=["d.session_file"],
    )
    yield ConstantField(
        str,
        "sessionfile",
        "path to session file",
        matcher=matching.PatternFilter,
        accessor=lambda o: os.path.expanduser(str(o.rpc_call("d.session_file"))),
        requires=["d.session_file"],
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
    )
    yield DynamicField(
        int,
        "uploaded",
        "amount of uploaded data",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: o.rpc_call("d.up.total"),
        requires=["d.up.total"],
    )
    yield DynamicField(
        int,
        "xfer",
        "transfer rate",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: o.fetch("up") + o.fetch("down"),
        requires=["d.up.rate", "d.down.rate"],
    )
    # last_xfer = DynamicField(int, "last_xfer", "last time data was transferred", matcher=matching.TimeFilter,
    #     accessor=lambda o: int(o.fetch("timestamp.last_xfer") or 0), formatter=fmt.iso_datetime_optional)
    yield DynamicField(
        int,
        "down",
        "download rate",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: o.rpc_call("d.down.rate"),
        requires=["d.down.rate"],
    )
    yield DynamicField(
        int,
        "up",
        "upload rate",
        matcher=matching.ByteSizeFilter,
        accessor=lambda o: o.rpc_call("d.up.rate"),
        requires=["d.up.rate"],
    )
    yield DynamicField(
        str,
        "throttle",
        "throttle group name (NULL=unlimited, NONE=global)",
        matcher=matching.PatternFilter,
        accessor=lambda o: o.rpc_call("d.throttle_name"),
        formatter=lambda v: v if v else "NONE",
        requires=["d.throttle_name"],
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
    )
    yield DynamicField(
        int,
        "started",
        "time download was FIRST started",
        matcher=matching.TimeFilterNotNull,
        accessor=lambda o: int(o.rpc_call("d.custom", ["tm_started"]) or "0", 10),
        formatter=fmt.iso_datetime_optional,
        requires=["d.custom=tm_started"],
    )
    yield DynamicField(
        untyped,
        "leechtime",
        "time taken from start to completion",
        matcher=matching.DurationFilter,
        accessor=lambda o: _interval_sum(o, end=o.completed)
        or _duration(o.started, o.completed),
        formatter=_fmt_duration,
        requires=["d.custom=tm_completed", "d.custom=tm_started"],
    )
    yield DynamicField(
        int,
        "completed",
        "time download was finished",
        matcher=matching.TimeFilterNotNull,
        accessor=lambda o: int(o.rpc_call("d.custom", ["tm_completed"]) or "0", 10),
        formatter=fmt.iso_datetime_optional,
        requires=["d.custom=tm_completed"],
    )
    yield DynamicField(
        untyped,
        "seedtime",
        "total seeding time after completion",
        matcher=matching.DurationFilter,
        accessor=lambda o: _interval_sum(o, start=o.completed)
        if o.rpc_call("d.complete")
        else None,
        formatter=_fmt_duration,
        requires=["d.custom=tm_completed", "d.complete"],
    )
    # active = DynamicField(int, "active", "last time a peer was connected", matcher=matching.TimeFilter,
    #    accessor=lambda o: int(o.fetch("timestamp.last_active") or 0), formatter=fmt.iso_datetime_optional)
    yield DynamicField(
        int,
        "stopped",
        "time download was last stopped or paused",
        matcher=matching.TimeFilterNotNull,
        accessor=lambda o: (_interval_split(o, only="P") + [(0, 0)])[0][1],
        formatter=fmt.iso_datetime_optional,
    )


class TorrentProxy:
    """A single download item."""

    @classmethod
    def add_manifold_attribute(cls, name):
        """Register a manifold engine attribute.

        @return: field definition object, or None if "name" isn't a manifold attribute.
        """
        if name.startswith("custom_"):
            try:
                return FieldDefinition.FIELDS[name]
            except KeyError:
                custom_name = name.split("_", 1)[1]
                field = DynamicField(
                    str,
                    name,
                    f"custom attribute {custom_name}",
                    matcher=matching.PatternFilter,
                    accessor=lambda o: o.rpc_call("d.custom", [custom_name]),
                    requires=[f"d.custom={custom_name}"],
                )
                setattr(cls, name, field)  # add field to all proxy objects

                return field
        elif name.startswith("kind_") and name[5:].isdigit():
            try:
                return FieldDefinition.FIELDS[name]
            except KeyError:
                # pylint: disable=raise-missing-from
                limit = int(name[5:].lstrip("0") or "0", 10)
                if limit > 100:
                    raise error.UserError(f"kind_N: N > 100 in {name!r}")
                field = DynamicField(
                    set,
                    name,
                    f"kinds of files that make up more than {limit}% of this item's size",
                    matcher=matching.TaggedAsFilter,
                    formatter=_fmt_tags,
                    requires=[f"kind_{limit}"],
                )
                setattr(cls, name, field)

                return field
        else:
            return None

    @classmethod
    def add_field(cls, field):
        """Add a custom field to the class"""
        setattr(cls, field.name, field)
        FieldDefinition.FIELDS[field.name] = field
        if isinstance(field, ConstantField):
            FieldDefinition.CONSTANT_FIELDS.add(field.name)

    @classmethod
    def add_core_fields(cls, *_, **__):
        """Add any custom fields defined in the configuration."""
        for field in core_fields():
            setattr(cls, field.name, field)
            FieldDefinition.FIELDS[field.name] = field
            if isinstance(field, ConstantField):
                FieldDefinition.CONSTANT_FIELDS.add(field.name)

    def __init__(self):
        """Initialize object."""
        self._fields = {}

    def __hash__(self):
        """Make item hashable for Python."""
        return self.hash

    def __eq__(self, other):
        """Compare items based on their infohash."""
        return other and self.hash == getattr(other, "hash", None)

    hash = ConstantField(str, "hash", "info hash", matcher=matching.PatternFilter)

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

    # TODO: metafile data cache (sqlite, shelve or maybe .ini)
    # cache data indexed by hash
    # store ctime per cache entry
    # scan metafiles of new hashes not yet in cache
    # on cache read, for unknown hashes setdefault() a purge date, then remove entries after a while
    # clear purge date for known hashes (unloaded and then reloaded torrents)
    # store a version marker and other global metadata in cache under key = None, so it can be upgraded
    # add option to pyroadmin to inspect the cache, mainly for debugging

    # TODO: created (metafile creation date, i.e. the bencoded field; same as downloaded if missing; cached by hash)
    # add .age formatter (age = " 1y 6m", " 2w 6d", "12h30m", etc.)


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
                infohash = self.viewname
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
