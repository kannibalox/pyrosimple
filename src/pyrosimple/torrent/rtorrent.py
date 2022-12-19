""" rTorrent Proxy.

    Copyright (c) 2009, 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""

import base64
import errno
import logging
import operator
import os
import shlex
import time
import urllib.parse

from functools import lru_cache, partial
from pathlib import Path
from typing import Callable, Dict, Generator, List, Optional, Set, Tuple, Union
from xmlrpc import client as xmlrpclib

import bencode
import jinja2

from pyrosimple import config, error
from pyrosimple.torrent import engine
from pyrosimple.util import fmt, matching, metafile, pymagic, rpc, traits
from pyrosimple.util.cache import ExpiringCache
from pyrosimple.util.parts import Bunch


# Prepare the jinja template environment at the module level
env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(
        [Path("~/.config/pyrosimple/templates/").expanduser()]
    ),
)
# Load filter methods from fmt submodule
env.filters.update(
    {
        name[4:]: method
        for name, method in fmt.__dict__.items()
        if name.startswith("fmt_")
    }
)


class CommaLexer(shlex.shlex):
    """Helper to split argument lists."""

    def __init__(self, text: str):
        shlex.shlex.__init__(self, text, None, True)
        self.whitespace += ","
        self.whitespace_split = True
        self.commenters = ""


class RtorrentItem(engine.TorrentProxy):
    """A single download item."""

    def __init__(
        self,
        engine_,
        fields,
        rpc_fields: Optional[Dict] = None,
        cache_expires: Optional[float] = None,
    ):
        """Initialize download item."""
        super().__init__()
        if cache_expires is None:
            cache_expires = float(config.settings.ITEM_CACHE_EXPIRATION)
        self._engine = engine_
        self._fields = ExpiringCache(
            static_keys=engine.FieldDefinition.CONSTANT_FIELDS, expires=cache_expires
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
        """Cache a stable expensive-to-get item value for later
        (optimized) retrieval."""
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

    def _get_kind(self, limit) -> Set[str]:
        """Get a set of dominant file types. The files must contribute
        at least C{limit}% to the item's total size.
        """
        histo = self.rpc_call("d.custom", ["kind"])

        if histo:
            # Parse histogram from cached field
            histo = [i.split("%_") for i in str(histo).split()]
            histo = [(int(val, 10), ext) for val, ext in histo]
        else:
            # Get file types
            histo = traits.get_filetypes(
                self._get_files(),
                path=operator.attrgetter("path"),
                size=operator.attrgetter("size"),
            )

            # Set custom cache field with value formatted like "80%_flac 20%_jpg" (sorted by percentage)
            histo_str = " ".join([f'{i[0]}%_{i[1].replace(" ", "_")}' for i in histo])
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
        return dict(self._fields)

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
        if engine.TorrentProxy.add_manifold_attribute(name) is None:
            raise AttributeError(name)
        value = getattr(self, name)
        self._fields[name] = value
        return value

    def __getattr__(self, name):
        return self.fetch(name)

    def datapath(self) -> Path:
        """Get an item's data path."""
        directory = self.rpc_call("d.directory")
        if self.rpc_call("d.is_multi_file"):
            path = Path(directory)
        else:
            path = Path(directory, self.rpc_call("d.name"))
        return path.expanduser()

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

        previous: List[str] = self.rpc_call("d.custom", ["tags"]).split()
        tagset = set(previous)
        for tag in tags.replace(",", " ").split():
            if tag.startswith("-"):
                tagset.discard(tag[1:])
            elif tag.startswith("+"):
                tagset.add(tag[1:])
            elif tag:
                tagset.add(tag)

        # Write back new tagset, if changed
        tagset.discard("")
        if list(tagset) != previous:
            new_tags = " ".join(sorted(tagset))
            self._make_it_so(
                f"setting changed tags {tagset!r} on",
                ["d.custom.set"],
                "tags",
                new_tags,
            )
            self._fields["custom_tags"] = new_tags

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

        if (name or "NONE") == self.rpc_call("d.throttle_name"):
            self._engine.LOG.debug(
                "Keeping throttle %r on torrent #%s",
                self.rpc_call("d.throttle_name"),
                self._fields["hash"],
            )
            return

        active = self.rpc_call("d.is_active")
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
                    f"Bad custom field assignment {key!r}, probably missing a '=' ({exc})"
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

    def move(self, dest: os.PathLike, move_func: Optional[Callable] = None):
        """Move files from one path to another. By default it will do
        a simple move of only related files while replicating the same
        directory structure, but `move_func` allows providing custom
        behavior"""
        if move_func is None:

            def _default_move(_item, src, dest):
                import shutil  # pylint: disable=import-outside-toplevel

                shutil.move(src, dest)

            move_func = _default_move
        if self.rpc_call("d.is_multi_file"):
            for f in self._get_files():
                src = Path(self.datapath(), f.path)
                move_func(self, src, Path(dest, f.path))
        else:
            move_func(self, self.datapath(), dest)

    def move_to_host(self, remote_url: str, copy: bool = False):
        """Migrate an item to a remote host"""

        # TODO allow skipping fast resume (which requires local access to FS)
        # FIXME invalidate all self-cached items after sending

        # TODO Generalize this overriding of query parameters
        parsed_url = urllib.parse.urlsplit(remote_url)
        queries = urllib.parse.parse_qs(parsed_url.query)
        rpc_protocol = queries.get("rpc", ["xml"])[0]
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
        torrent = metafile.Metafile(
            bencode.decode(
                base64.b64decode(
                    proxy.execute.capture(
                        rpc.NOHASH,
                        "base64",
                        str(torrent_path),
                    )
                )
            )
        )
        try:
            torrent.add_fast_resume(Path(proxy.d.directory_base(self.hash)))
        except (FileNotFoundError, OSError) as e:
            self._engine.LOG.error("Could not add fast resume data: %s", e)
        # Do some basic escaping, nothing else should be necessary.
        base_dir = proxy.d.directory_base(self.hash).replace('"', r"\"")
        extra_cmds.insert(0, f'd.directory_base.set="{base_dir}"')
        rpc_metafile = xmlrpclib.Binary(bencode.bencode(dict(torrent)))
        if not copy:
            proxy.d.stop(self.hash)
        self._engine.LOG.debug("Running extra commands on load: %s", extra_cmds)
        if rpc_protocol == "json":
            remote_proxy.load.verbose("", rpc_metafile, *extra_cmds)
        else:
            remote_proxy.load.raw_verbose("", rpc_metafile, *extra_cmds)
        for _ in range(0, 10):
            try:
                remote_proxy.d.hash(self.hash)
                break
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
        tied_file = self.rpc_call("d.tied_to_file")
        if tied_file:
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
        path = Path(self.rpc_call("d.directory"))
        if not path.is_absolute():
            raise error.EngineError(
                f"Directory '{path}' for item {self.hash} is not absolute, which is a bad idea,"
                " fix your .rtorrent.rc to use 'directory.default.set = /...'"
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
        self.startup = time.time()
        self.rpc = None
        self.properties = {}
        self.known_throttle_names = {"", "NULL"}
        self.url: str
        if url is None:
            config.autoload_scgi_url()
            self.url = config.settings.SCGI_URL
        else:
            self.url = url
        if auto_open:
            self.open()

    def view(self, viewname="default", matcher=None):
        """Get list of download items."""
        return engine.TorrentView(self, viewname, matcher)

    def __repr__(self):
        """Return a representation of internal state."""
        if self.rpc:
            # Connected state
            return "{} connected to {} [{}, up {}] via {!r}".format(
                self.__class__.__name__,
                self.engine_id,
                self.engine_software,
                fmt.human_duration(self.uptime, 0, 2, True).strip(),
                self.url,
            )
        # Unconnected state
        return "{} connectable via {!r}".format(
            self.__class__.__name__,
            self.url,
        )

    @property
    def uptime(self):
        """rTorrent's uptime."""
        return time.time() - self.startup

    def _resolve_viewname(self, viewname: str) -> str:
        """Check for special view names and return existing rTorrent one."""
        if viewname == "-":
            try:
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
            results[list(methods.keys())[index]] = r[0]
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
        if not self.url:
            raise error.UserError(
                "You need to configure a RPC connection, read"
                " https://kannibalox.github.io/pyrosimple/configuration/#top-level-section"
            )

        # Connect and get instance ID (also ensures we're connectable)
        self.rpc = rpc.RTorrentProxy(self.url)
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
                "Unsupported xmlrpc-c version (64 bit integer support missing,"
                " %r returned instead)",
                type(time_usec),
            )

        # Get other manifest values
        self.engine_software = f"rTorrent {self.properties['system.library_version']}/{self.properties['system.client_version']}"

        try:
            self.startup = int(self.rpc.startup_time() or time.time())
        except xmlrpclib.Fault:
            self.startup = int(time.time())

        # Return connection
        self.LOG.debug("%s", repr(self))
        return self.rpc

    def multicall(self, viewname: str, fields: List[str]) -> List[Bunch]:
        """Query the given fields of items in the given view.

        The result list contains named tuples,
        so you can access the fields directly by their name.
        """
        commands = tuple(f"d.{x}=" for x in fields)
        items = self.open().d.multicall2("", viewname, *commands)
        return [
            Bunch(dict(zip([x.replace(".", "_") for x in fields], item)))
            for item in items
        ]

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

        if view is None:
            view = engine.TorrentView(self, "default")
        elif isinstance(view, str):
            view = engine.TorrentView(self, self._resolve_viewname(view))

        # Map pyroscope names to rTorrent ones
        if prefetch:
            prefetch = self.BASE_FIELDS | set(prefetch)
        else:
            prefetch = self.PREFETCH_FIELDS

        # Fetch items
        items = []
        multi_args: List
        try:
            # Prepare multi-call arguments
            args = sorted(prefetch)

            # Check if view is in the format of a single hash
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
                raw_items = [[i[0] for i in multi_call(multi_args)]]
            # Otherwise prepare a multicall as expected
            else:
                multi_call = self.open().d.multicall2
                multi_args = ["", view.viewname] + [
                    field if "=" in field else field + "=" for field in args
                ]
                if view.matcher and int(config.settings.get("FAST_QUERY")) > 0:
                    pre_filter = ""
                    if config.settings.SAFETY_CHECKS_ENABLED and not self.has_method(
                        "d.multicall.filtered"
                    ):
                        self.LOG.warning(
                            "Fast query enabled but host does not support 'd.multicall.filtered', disabling fast query."
                        )
                    else:
                        pre_filter = matching.unquote_pre_filter(
                            view.matcher.pre_filter()
                        )
                    if pre_filter:
                        # rTorrent 0.9.8+ does not have
                        # sting.contains_i, so we check for it here
                        self.LOG.info("!!! pre-filter: %s", pre_filter or "N/A")
                        if (
                            config.settings.SAFETY_CHECKS_ENABLED
                            and "string.contains_i" in pre_filter
                            and not self.has_method("string.contains_i")
                        ):
                            self.LOG.warning(
                                "Method 'strings.contains_i' does not exist!"
                                "Fast query %r would return an empty list, disabling fast query.",
                                pre_filter,
                            )
                        else:
                            multi_call = self.open().d.multicall.filtered
                            multi_args.insert(2, pre_filter)
                raw_items = multi_call(*tuple(multi_args))

            self.LOG.debug(
                "Got %d items with %d attributes",
                len(raw_items),
                len(prefetch),
            )

            # Build objects from the received data
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
        """Place a set of items (search result) into a view, and
        return the view name."""
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
        for item in items:
            if disjoin:
                proxy.d.views.remove(item.hash, view_name)
                proxy.view.set_not_visible(item.hash, view_name)
            else:
                proxy.d.views.push_back_unique(item.hash, view_name)
                proxy.view.set_visible(item.hash, view_name)

        return view


def expand_template(template_path: str, namespace: Dict) -> str:
    """Expand the given template file.
    Currently, only jinja2 templates are supported.

    @param template: The name of the template, to be loaded by the jinja2 loaders.
    @param namespace: Custom namespace that is added to the predefined defaults
        and takes precedence over those.
    @return: The expanded template.
    @raise LoggableError: In case of typical errors during template execution.
    """
    template = env.get_template(template_path)
    # Default templating namespace
    # variables = dict(c=config.custom_template_helpers)
    variables = {}
    # Provided namespace takes precedence
    variables.update(namespace)
    # Expand template
    return template.render(**variables)


def format_item_str(
    template_str: str, item: Union[Dict, str, RtorrentItem], defaults=None
):
    """Simple helper function to format a string with an item"""
    template = env.from_string(template_str)
    return format_item(template, item, defaults)


def format_item(
    template: jinja2.Template,
    item: Union[Dict, str, RtorrentItem],
    defaults: Optional[Dict] = None,
) -> str:
    """Format an item according to the given output template.

    @param format_spec: The output template, preparsed by jinja2.
    @param item: The object, which is automatically wrapped for interpolation.
    @param defaults: Optional default values.
    """
    if defaults is None:
        defaults = {}
    return str(template.render(d=item, **defaults))


def validate_field_list(
    fields: str,
    allow_fmt_specs=False,
):
    """Make sure the fields in the given list exist.

    @param fields: List of fields (comma-/space-separated if a string).
    @type fields: list or str
    @return: validated field names.
    @rtype: list
    """
    try:
        split_fields = [i.strip() for i in fields.split(",")]
    except AttributeError:
        # Not a string, expecting an iterable
        pass

    for name in split_fields:
        if allow_fmt_specs and "." in name:
            fullname = name
            name, fmtspecs = name.split(".", 1)
            for fmtspec in fmtspecs.split("."):
                if fmtspec not in env.filters and fmtspec != "raw":
                    raise error.UserError(
                        f"Unknown format specification {fmtspec!r} in {fullname!r}"
                    )

        if (
            name not in engine.FIELD_REGISTRY
            and not engine.TorrentProxy.add_manifold_attribute(name)
        ):
            raise error.UserError(f"Unknown field name {name!r}")

    return split_fields


def validate_sort_fields(sort_fields: str):
    """Make sure the fields in the given list exist, and return sorting key.

    If field names are prefixed with '-', sort order is reversed for that field (descending).
    """
    # Create sort specification
    sort_spec: Tuple = tuple()
    for name in sort_fields.split(","):
        descending = False
        if name.startswith("-"):
            name = name[1:]
            descending = True
        sort_spec += ((name, descending),)

    # Validate field list
    validate_field_list(",".join([name for name, _ in sort_spec]))
    logger = logging.getLogger(__name__)
    logger.debug(
        "Validated key names: %s",
        ", ".join([("-" if descending else "") + i for i, descending in sort_spec]),
    )

    # Need to provide complex key in order to allow for the minimum
    # amount of attribute fetches, since they could mean a potentially
    # expensive RPC call.
    class Key:
        "Complex sort order key"

        def __init__(self, obj, *_):
            "Remember object to be compared"
            self.obj = obj

        def __lt__(self, other):
            "Compare to other key"
            for field, descending in sort_spec:
                lhs, rhs = getattr(self.obj, field), getattr(other.obj, field)
                if lhs == rhs:
                    continue
                return rhs < lhs if descending else lhs < rhs
            return False

    return Key


def get_fields_from_template(
    template: str, item_name: str = "d"
) -> Generator[str, None, None]:
    """Utility function to get field references from a template

    E.g: 'Size: {{d.size}}' -> ['size']"""
    for node in env.parse(template).find_all(jinja2.nodes.Getattr):
        if isinstance(node.node, jinja2.nodes.Name) and node.node.name == item_name:
            yield node.attr
