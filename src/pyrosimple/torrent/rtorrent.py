""" rTorrent Proxy.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""

import base64
import errno
import operator
import os
import shlex
import time

from collections import defaultdict
from functools import lru_cache, partial
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Union
from xmlrpc import client as xmlrpclib

import bencode

from pyrosimple import config, error
from pyrosimple.torrent import engine
from pyrosimple.util import fmt, matching, metafile, pymagic, rpc, traits
from pyrosimple.util.cache import ExpiringCache
from pyrosimple.util.parts import Bunch


class CommaLexer(shlex.shlex):
    """Helper to split argument lists."""

    def __init__(self, text: str):
        shlex.shlex.__init__(self, text, None, True)
        self.whitespace += ","
        self.whitespace_split = True
        self.commenters = ""


class RtorrentItem(engine.TorrentProxy):
    """A single download item."""

    def __init__(self, engine_, fields, rpc_fields: Optional[Dict] = None):
        """Initialize download item."""
        super().__init__()
        self._engine = engine_
        self._fields = ExpiringCache(
            static_keys=engine.FieldDefinition.CONSTANT_FIELDS
        )  # Acts a cache for the item
        self._fields.update(dict(fields))
        self._rpc_cache = ExpiringCache(
            static_keys={
                "d.name",
                "d.size_bytes",
                "d.size_chunks",
            }
        )
        if rpc_fields is not None:
            self._rpc_cache.update(rpc_fields)
        if "hash" not in fields:
            self._fields["hash"] = self.rpc_call("d.hash")

    def _make_it_so(
        self, command: str, calls: List[str], *args, observer: Optional[Callable] = None
    ):
        """Perform some error-checked RPC calls."""
        args = (self._fields["hash"],) + args
        try:
            self._engine.LOG.debug(
                "%s%s torrent %s",
                command[0].upper(),
                command[1:],
                self._fields["hash"],
            )
            for call in calls:
                namespace = self._engine.rpc
                result = getattr(namespace, call.lstrip(":"))(*args)
                if observer is not None:
                    observer(result)
        except rpc.ERRORS as exc:
            raise error.EngineError(
                f"While {command} torrent {self._fields['hash']}: {exc}"
            )

    def _get_files(self, attrs: Optional[List[str]] = None):
        """Get a list of all files in this download; each entry has the
        attributes C{path} (relative to root), C{size} (in bytes),
        C{mtime}, C{prio} (0=off, 1=normal, 2=high), C{created},
        and C{opened}.

        @param attrs: Optional list of additional attributes to fetch.
        """
        try:
            # Get info for all files
            f_multicall = self._engine.rpc.f.multicall
            f_params = [
                self._fields["hash"],
                rpc.NOHASH,
                "f.path=",
                "f.size_bytes=",
                "f.last_touched=",
                "f.priority=",
                "f.is_created=",
                "f.is_open=",
            ]
            for attr in attrs or []:
                f_params.append(f"f.{attr}=")
            rpc_result = f_multicall(*tuple(f_params))
        except rpc.ERRORS as exc:
            raise error.EngineError(
                f"While getting files for torrent #{self._fields['hash']}: {exc}"
            )
        else:
            # self._engine.LOG.debug("files result: %r" % rpc_result)

            # Return results
            result = [
                Bunch(
                    path=i[0],
                    size=i[1],
                    mtime=i[2] / 1000000.0,
                    prio=i[3],
                    created=i[4],
                    opened=i[5],
                )
                for i in rpc_result
            ]

            if attrs:
                for idx, attr in enumerate(attrs):
                    for item, rpc_item in zip(result, rpc_result):
                        item[attr] = rpc_item[6 + idx]

            return result

    def memoize(self, name: str, getter: Callable, *args, **kwargs):
        """Cache a stable expensive-to-get item value for later (optimized) retrieval."""
        field = "custom_memo_" + name
        cached = self.rpc_call("d.custom", ["memo_" + name])
        if cached:
            value = cached
        else:
            value = getter(*args, **kwargs)
            self._make_it_so(
                f"caching {name}={value!r} for",
                ["d.custom.set"],
                field[7:],
                value,
            )
            self._fields[field] = value
        return value

    def _get_kind(self, limit):
        """Get a set of dominant file types. The files must contribute
        at least C{limit}% to the item's total size.
        """
        histo = self.fetch("custom_kind")

        if histo:
            # Parse histogram from cached field
            histo = [i.split("%_") for i in str(histo).split()]
            histo = [(int(val, 10), ext) for val, ext in histo]
            ##self._engine.LOG.debug("~~~~~~~~~~ cached histo = %r" % histo)
        else:
            # Get filetypes
            histo = traits.get_filetypes(
                self.fetch("files"),
                path=operator.attrgetter("path"),
                size=operator.attrgetter("size"),
            )

            # Set custom cache field with value formatted like "80%_flac 20%_jpg" (sorted by percentage)
            histo_str = " ".join(("%d%%_%s" % i).replace(" ", "_") for i in histo)
            self._make_it_so(
                f"setting kind cache {histo_str!r} on",
                ["d.custom.set"],
                "kind",
                histo_str,
            )
            self._fields["custom_kind"] = histo_str

        # Return all non-empty extensions that make up at least <limit>% of total size
        return {ext for val, ext in histo if ext and val >= limit}

    def as_dict(self):
        """Return known fields."""
        return self._fields.copy()

    def rpc_call(self, method: str, args: Optional[List] = None, cache: bool = True):
        """Directly call rpc for item-specific information"""
        cache_key = method
        if args:
            cache_key += "=" + ",".join([str(a) for a in args])
        val = self._rpc_cache.get(cache_key, None)
        if cache and val is not None:
            return val
        if args is None:
            args = []
        getter = getattr(self._engine.rpc, method)
        val = getter(self._fields["hash"], *args)
        self._rpc_cache[cache_key] = val
        return val

    def fetch(self, name: str, cache: bool = True):
        """Get a field on demand. By 'on demand', this means that the field may possibly be created
        if it does not already exists (e.g. custom fields). It also allows directly controlling if the _fields cache
        should be used"""
        if cache:
            try:
                return self._fields[name]
            except KeyError:
                pass
        if isinstance(name, int):
            name = "custom_%d" % name
        if name.startswith("kind_") and name[5:].isdigit():
            val = self._get_kind(int(name[5:], 10))
        elif name.startswith("custom_"):
            key = name[7:]
            try:
                if len(key) == 1 and key in "12345":
                    val = getattr(self._engine.rpc.d, "custom" + key)(
                        self._fields["hash"]
                    )
                else:
                    val = self._engine.rpc.d.custom(self._fields["hash"], key)
            except rpc.ERRORS as exc:
                raise error.EngineError(f"While accessing field {name!r}: {exc}")
        else:
            val = getattr(self, name)

        self._fields[name] = val

        return val

    def datapath(self) -> Path:
        """Get an item's data path."""
        path = self.rpc_call("d.directory")
        if path and not self.rpc_call("d.is_multi_file"):
            path = os.path.join(path, self.rpc_call("d.name"))
        path = os.path.expanduser(path)
        if self.rpc_call("d.is_multi_file"):
            return Path(path)
        return Path(path)

    def announce_urls(self, default=[]):  # pylint: disable=dangerous-default-value
        """Get a list of all announce URLs.
        Returns `default` if no trackers are found at all.
        """
        try:
            response = self.rpc_call("t.multicall", ["", "t.url=", "t.is_enabled="])
        except rpc.ERRORS as exc:
            raise error.EngineError(
                f"While getting announce URLs for #{self._fields['hash']}: {exc}"
            )

        if response:
            return [i[0] for i in response if i[1]]
        return default

    def start(self):
        """(Re-)start downloading or seeding."""
        self._make_it_so("starting", ["d.open", "d.start"])

    def stop(self):
        """Stop and close download."""
        self._make_it_so("stopping", ["d.stop", "d.close"])

    def ignore(self, flag: int):
        """Set ignore status."""
        self._make_it_so("setting ignore status for", ["d.ignore_commands.set"], flag)
        self._fields["is_ignored"] = flag

    def set_prio(self, prio: int):
        """Set priority (0-3)."""
        self._make_it_so(
            "setting priority for", ["d.priority.set"], max(0, min(int(prio), 3))
        )

    def tag(self, tags: str):
        """Add or remove tags."""
        # Get tag list and add/remove given tags
        tags = tags.lower()
        previous = self.fetch("tagged")
        tagset = previous.copy()
        for tag in tags.replace(",", " ").split():
            if tag.startswith("-"):
                tagset.discard(tag[1:])
            elif tag.startswith("+"):
                tagset.add(tag[1:])
            else:
                tagset.add(tag)

        # Write back new tagset, if changed
        tagset.discard("")
        if tagset != previous:
            tagset = " ".join(sorted(tagset))
            self._make_it_so(
                f"setting tags {tagset!r} on", ["d.custom.set"], "tags", tagset
            )
            self._fields["custom_tags"] = tagset

    def set_throttle(self, name: str):
        """Assign to throttle group."""
        if name.lower() == "null":
            name = "NULL"
        if name.lower() == "none":
            name = ""

        if name not in self._engine.known_throttle_names:
            if self._engine.rpc.throttle.up.max(rpc.NOHASH, name) == -1:
                if self._engine.rpc.throttle.down.max(rpc.NOHASH, name) == -1:
                    raise error.UserError(f"Unknown throttle name '{name}'")
            self._engine.known_throttle_names.add(name)

        if (name or "NONE") == self.fetch("throttle"):
            self._engine.LOG.debug(
                "Keeping throttle %r on torrent #%s",
                self.fetch("throttle"),
                self._fields["hash"],
            )
            return

        active = self.fetch("is_active")
        if active:
            self._engine.LOG.debug(
                "Torrent #%s stopped for throttling", self._fields["hash"]
            )
            self.stop()
        self._make_it_so(f"setting throttle {name!r} on", ["d.throttle_name.set"], name)
        if active:
            self._engine.LOG.debug(
                "Torrent #%s restarted after throttling",
                self._fields["hash"],
            )
            self.start()

    def set_custom(self, key: str, value: Optional[str] = None):
        """Set a custom value. C{key} might have the form "key=value" when value is C{None}."""
        # Split combined key/value
        if value is None:
            try:
                key, value = key.split("=", 1)
            except (ValueError, TypeError) as exc:
                raise error.UserError(
                    "Bad custom field assignment %r, probably missing a '=' (%s)"
                    % (key, exc)
                )

        # Check identifier rules
        args: List[str]
        if not key:
            raise error.UserError("Custom field name cannot be empty!")
        if len(key) == 1 and key in "12345":
            method, args = "d.custom" + key + ".set", [value]
        elif not (key[0].isalpha() and key.replace("_", "").isalnum()):
            raise error.UserError(
                f"Bad custom field name {key!r} (must only contain a-z, A-Z, 0-9 and _)"
            )
        else:
            method, args = "d.custom.set", [key, value]

        # Make the assignment
        self._make_it_so(f"setting custom_{key} = {value!r} on", [method], *args)
        self._fields["custom_" + key] = value

    def hash_check(self):
        """Hash check a download."""
        self._make_it_so("hash-checking", ["d.check_hash"])

    def __print_result(self, data, method=None, args=None):
        "Helper to print RPC call results"
        args_list = ""
        if args:
            args_list = '"' + '","'.join(args) + '"'
        print(f"{self._fields['hash']}\t{data}\t{method.lstrip(':')}={args_list}")

    def execute(self, commands):
        """Execute RPC command(s)."""
        try:
            commands = [i.strip() for i in commands.split(" ; ")]
        except (TypeError, AttributeError):
            pass  # assume an iterable

        for command in commands:
            try:
                method, args = command.split("=", 1)
                args = tuple(CommaLexer(args))
            except (ValueError, TypeError) as exc:
                raise error.UserError(
                    f"Bad command {command!r}, probably missing a '=' ({exc})"
                )

            observer = None
            if method.startswith(">"):
                observer = partial(self.__print_result, args=args, method=method)
            method = method.lstrip(">")
            self._make_it_so("executing command on", [method], *args, observer=observer)

    def custom_items(self) -> Dict:
        """Try using rtorrent-ps commands to list custom keys, otherwise fall back to reading from a session file.

        This does *not* include the custom1, custom2, etc. keys"""
        proxy = self._engine.open()
        if self._engine.has_method("d.custom.keys"):
            custom_fields = {}
            for key in proxy.d.custom.keys(self.hash):
                custom_fields[key] = proxy.d.custom(self.hash, key)
            return custom_fields
        proxy.d.save_full_session(self.hash)
        info_file = Path(proxy.session.path(), f"{self.hash}.torrent.rtorrent")
        return dict(
            bencode.decode(proxy.execute.capture(rpc.NOHASH, "cat", info_file))[
                "custom"
            ]
        )

    def move_to_host(self, remote_url: str, copy: bool = False):
        """Migrate an item to a remote host

        TODO allow skipping fast resume (which requires local access to FS)
        FIXME invalidate all self-cached items after sending"""
        remote_proxy = RtorrentEngine(remote_url).open()
        proxy = self._engine.open()
        self._engine.LOG.debug("Attempting to move %s to %s", self.hash, remote_url)
        extra_cmds: List[str] = []
        try:
            remote_proxy.d.hash(self.hash)
        except rpc.HashNotFound:
            pass
        else:
            raise error.EngineError(
                f"Hash {self.hash} already exists remotely on {remote_url}"
            )
        # This might be brittle for systems that have a low network.xmlrpc.size_limit but large torrents.
        torrent_path = Path(proxy.session.path(), f"{self.hash}.torrent")
        torrent = bencode.decode(
            base64.b64decode(
                proxy.execute.capture(
                    rpc.NOHASH,
                    "base64",
                    str(torrent_path),
                )
            )
        )
        metafile.add_fast_resume(torrent, proxy.d.directory_base(self.hash))
        # Do some basic escaping, nothing else should be necessary.
        base_dir = proxy.d.directory_base(self.hash).replace('"', r"\"")
        extra_cmds.insert(0, f'd.directory_base.set="{base_dir}"')
        rpc_metafile = xmlrpclib.Binary(bencode.bencode(torrent))
        if not copy:
            proxy.d.stop(self.hash)
        self._engine.LOG.debug("Running extra commands on load: %s", extra_cmds)
        remote_proxy.load.raw_verbose("", rpc_metafile, *extra_cmds)
        for _ in range(0, 10):
            try:
                remote_proxy.d.hash(self.hash)
            except rpc.HashNotFound:
                time.sleep(0.5)
        # After 5 seconds, let the exception happen
        remote_proxy.d.hash(self.hash)

        # Keep custom values
        # Trying to load these in during the load.raw tends to cause either the load to fail
        # or the values to get corrupted, even for simple values.
        for k, v in self.custom_items().items():
            remote_proxy.d.custom.set(self.hash, k, v)
        for key in range(1, 5):
            value = getattr(proxy.d, f"custom{key}")(self.hash)
            if value:
                getattr(remote_proxy.d, f"custom{key}.set")(self.hash, value)

        remote_proxy.d.start(self.hash)
        if not copy:
            proxy.d.erase(self.hash)
        return True

    def delete(self):
        """Remove torrent from client."""
        self.stop()
        if self.fetch("metafile"):
            self._make_it_so("removing metafile of", ["d.delete_tied"])
        self._make_it_so("erasing", ["d.erase"])

    # TODO: def set_files_priority(self, pattern, prio)
    # Set priority of selected files
    # NOTE: need to call d.update_priorities after f.priority.set!

    def purge(self):
        """Delete PARTIAL data files and remove torrent from client."""

        def partial_file(item):
            "Filter out partial files"
            return item.completed_chunks < item.size_chunks

        self.cull(file_filter=partial_file, attrs=["completed_chunks", "size_chunks"])

    def cull(self, file_filter: Optional[Callable] = None, attrs: List[str] = None):
        """Delete ALL data files and remove torrent from client.

        @param file_filter: Optional callable for selecting a subset of all files.
            The callable gets a file item as described for RtorrentItem._get_files
            and must return True for items eligible for deletion.
        @param attrs: Optional list of additional attributes to fetch (for
            file_filter to use).
        """
        dry_run = False  # set to True for testing
        path = Path(self.fetch("directory"))
        if not path.is_absolute():
            raise error.EngineError(
                "Directory '%s' for item %s is not absolute, which is a bad idea,"
                " fix your .rtorrent.rc to use 'directory.default.set = /...'"
                % (self.fetch("directory"), self._fields["hash"])
            )

        if not path.exists():
            return

        dirs_to_clean_up = set([path])
        for file_data in self._get_files(attrs=attrs):
            if file_filter is not None and not file_filter(file_data):
                continue
            fullpath = Path(path, file_data.path)
            if fullpath.is_file() or fullpath.is_symlink():
                self._engine.LOG.debug("Deleting '%s'", fullpath)
                dirs_to_clean_up.add(fullpath.parent)
                if not dry_run:
                    fullpath.unlink()
        for directory in dirs_to_clean_up:
            try:
                if not dry_run:
                    directory.rmdir()
            except OSError as e:
                if e.errno != errno.ENOTEMPTY:
                    raise

        # Delete item from engine
        if not dry_run:
            self.delete()

    def flush(self):
        """Write volatile data to disk."""
        self._make_it_so("saving session data of", ["d.save_resume"])


class RtorrentEngine:
    """The rTorrent backend proxy."""

    # Bare minimum fields to prefetch
    BASE_FIELDS = {
        "d.hash",
    }

    # rTorrent names of fields that never change
    CONSTANT_FIELDS = BASE_FIELDS | {
        "d.name",
        "d.is_private",
        "d.is_multi_file",
        "d.tracker_size",
        "d.size_bytes",
    }

    # rTorrent names of fields that need to be pre-fetched
    CORE_FIELDS = CONSTANT_FIELDS | {
        "d.complete",
        "d.tied_to_file",
    }

    # rTorrent names of fields that get fetched in multi-call
    PREFETCH_FIELDS = CORE_FIELDS | {
        "d.base_path",
        "d.custom=memo_alias",
        "d.custom=tm_completed",
        "d.custom=tm_loaded",
        "d.custom=tm_started",
        "d.down.rate",
        "d.down.total",
        "d.is_active",
        "d.is_open",
        "d.message",
        "d.ratio",
        "d.up.rate",
        "d.up.total",
    }

    def __init__(self, url=None, auto_open=False):
        """Initialize proxy."""
        self.LOG = pymagic.get_class_logger(self)
        self.engine_id = "N/A"  # ID of the instance we're connecting to
        self.engine_software = "rTorrent"  # Name and version of software
        self.versions = (None, None)
        self.version_info = (0,)
        self.startup = time.time()
        self.rpc = None
        self.properties = {}
        self._item_cache = {}
        self.known_throttle_names = {"", "NULL"}
        if url is None:
            config.autoload_scgi_url()
        else:
            config.settings.SCGI_URL = url
        if auto_open:
            self.open()

    def view(self, viewname="default", matcher=None):
        """Get list of download items."""
        return engine.TorrentView(self, viewname, matcher)

    def group_by(self, fields, items=None):
        """Returns a dict of lists of items, grouped by the given fields.

        ``fields`` can be a string (one field) or an iterable of field names.
        """
        result = defaultdict(list)
        if items is None:
            items = self.items()

        try:
            key = operator.attrgetter(fields + "")
        except TypeError:

            def key(obj, names=tuple(fields)):
                "Helper to return group key tuple"
                return tuple(getattr(obj, x) for x in names)

        for item in items:
            result[key(item)].append(item)

        return result

    def __repr__(self):
        """Return a representation of internal state."""
        if self.rpc:
            # Connected state
            return "{} connected to {} [{}, up {}] via {!r}".format(
                self.__class__.__name__,
                self.engine_id,
                self.engine_software,
                fmt.human_duration(self.uptime, 0, 2, True).strip(),
                config.settings.SCGI_URL,
            )
        # Unconnected state
        return "{} connectable via {!r}".format(
            self.__class__.__name__,
            config.settings.SCGI_URL,
        )

    @property
    def uptime(self):
        """rTorrent's uptime."""
        return time.time() - self.startup

    def _resolve_viewname(self, viewname: str) -> str:
        """Check for special view names and return existing rTorrent one."""
        if viewname == "-":
            try:
                # Only works with rTorrent-PS at this time!
                viewname = self.open().ui.current_view()
            except rpc.ERRORS as exc:
                raise error.EngineError(f"Can't get name of current view: {exc}")

        return viewname

    def system_multicall(self, methods: Dict[str, List]) -> Dict:
        """Helper method for system.multicall"""
        results = {}
        call = []
        for method, params in methods.items():
            call.append({"methodName": method, "params": params})
        for index, r in enumerate(self.rpc.system.multicall(call)):
            if len(r) == 1:
                result = r[0]
            results[list(methods.keys())[index]] = result
        return results

    @lru_cache(maxsize=32)
    def has_method(self, method_name: str):
        """Cached check to see if method exists"""
        if method_name in self.rpc.system.listMethods():
            return True
        return False

    def open(self):
        """Open connection."""
        # Only connect once
        if self.rpc is not None:
            return self.rpc

        # Reading abilities are on the downfall, so...
        if not config.settings.SCGI_URL:
            raise error.UserError(
                "You need to configure a RPC connection, read"
                " https://pyrosimple.readthedocs.io/en/latest/setup.html"
            )

        # Connect and get instance ID (also ensures we're connectable)
        self.rpc = rpc.RTorrentProxy(config.settings.SCGI_URL)
        self.properties = self.system_multicall(
            {
                "system.client_version": [],
                "system.library_version": [],
                "system.time_usec": [],
                "session.name": [],
                "directory.default": [],
                "session.path": [],
            }
        )
        self.engine_id = self.properties["session.name"]
        time_usec = self.properties["system.time_usec"]

        # Make sure xmlrpc-c works as expected
        if time_usec < 2**32:
            self.LOG.warning(
                "Your xmlrpc-c is broken (64 bit integer support missing,"
                " %r returned instead)",
                type(time_usec),
            )

        # Get other manifest values
        self.engine_software = f"rTorrent {self.properties['system.library_version']}/{self.properties['system.client_version']}"

        if "+ssh:" in config.settings.SCGI_URL:
            self.startup = int(self.rpc.startup_time() or time.time())
        else:
            lockfile = os.path.join(self.properties["session.path"], "rtorrent.lock")
            try:
                self.startup = int(
                    self.rpc.execute.capture("", ["stat", "-c", "%Y", lockfile])
                )
            except (ValueError, xmlrpclib.Fault):
                self.startup = time.time()

        # Return connection
        self.LOG.debug("%s", repr(self))
        return self.rpc

    def multicall(self, viewname: str, fields: List[str]) -> Bunch:
        """Query the given fields of items in the given view.

        The result list contains named tuples,
        so you can access the fields directly by their name.
        """
        commands = tuple(f"d.{x}=" for x in fields)
        items = self.open().d.multicall2("", viewname, *commands)
        return Bunch(dict(zip([x.replace(".", "_") for x in fields], items)))

    def log(self, msg: str):
        """Log a message in the torrent client."""
        self.open().log(rpc.NOHASH, msg)

    def item(self, infohash: str, prefetch=None):
        """Fetch a single item by its info hash."""
        return next(self.items(infohash, prefetch))

    def items(
        self,
        view: Optional[Union[engine.TorrentView, str]] = None,
        prefetch: Optional[Set[str]] = None,
    ):
        """Get list of download items.

        @param view: Name of the view.
        @param prefetch: Optional list of field names to fetch initially.
        """

        multi_args: List
        if view is None:
            view = engine.TorrentView(self, "default")
        elif isinstance(view, str):
            view = engine.TorrentView(self, self._resolve_viewname(view))
        else:
            view.viewname = self._resolve_viewname(view.viewname)

        # Map pyroscope names to rTorrent ones
        if prefetch:
            prefetch = self.BASE_FIELDS | set(prefetch)
        else:
            prefetch = self.PREFETCH_FIELDS

        # Fetch items
        items = []
        try:
            # Prepare multi-call arguments
            args = sorted(prefetch)

            infohash = view._check_hash_view()
            if infohash:
                multi_call = self.open().system.multicall
                multi_args = [
                    dict(
                        methodName=field.rsplit("=", 1)[0],
                        params=[infohash]
                        + (field.rsplit("=", 1)[1].split(",") if "=" in field else []),
                    )
                    for field in args
                ]
                raw_items = [[i[0] for i in multi_call(args)]]
            else:
                multi_call = self.open().d.multicall2
                multi_args = ["", view.viewname] + [
                    field if "=" in field else field + "=" for field in args
                ]
                if view.matcher and config.settings.get("FAST_QUERY"):
                    pre_filter = matching.unquote_pre_filter(view.matcher.pre_filter())
                    self.LOG.info("!!! pre-filter: %s", pre_filter or "N/A")
                    if pre_filter:
                        multi_call = self.open().d.multicall.filtered
                        multi_args.insert(2, pre_filter)
                raw_items = multi_call(*tuple(multi_args))

            self.LOG.debug(
                "Got %d items with %d attributes from %r [%s]",
                len(raw_items),
                len(prefetch),
                self.engine_id,
                multi_call,
            )

            for item in raw_items:
                ritem = RtorrentItem(
                    self,
                    fields={},
                    rpc_fields=dict(zip(args, item)),
                )

                if view.matcher:
                    if view.matcher.match(ritem):
                        items.append(ritem)
                        yield items[-1]
                else:
                    items.append(ritem)
                    yield items[-1]
        except rpc.ERRORS as exc:
            raise error.EngineError(
                f"While getting download items from {self!r}: {exc}"
            )

    def show(
        self,
        items,
        view: Optional[str] = None,
        append: bool = False,
        disjoin: bool = False,
    ):
        """Visualize a set of items (search result), and return the view name."""
        proxy = self.open()
        view_name: str = self._resolve_viewname(view or "rtcontrol")

        if append and disjoin:
            raise error.EngineError(
                f"Cannot BOTH append to / disjoin from view '{view_name}'"
            )

        # Add view if needed
        if view not in proxy.view.list():
            proxy.view.add(rpc.NOHASH, view_name)

        # Clear view and show it
        if not append and not disjoin:
            proxy.view.filter(rpc.NOHASH, view_name, "false=")
            proxy.d.multicall2(rpc.NOHASH, "default", "d.views.remove=" + view_name)
        proxy.ui.current_view.set(rpc.NOHASH, view_name)

        # Add items
        # TODO: should be a "system.multicall"
        for item in items:
            if disjoin:
                proxy.d.views.remove(item.hash, view_name)
                proxy.view.set_not_visible(item.hash, view_name)
            else:
                proxy.d.views.push_back_unique(item.hash, view_name)
                proxy.view.set_visible(item.hash, view_name)

        return view
