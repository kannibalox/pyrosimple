""" Move seeding data.

    Copyright (c) 2010, 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
import os

from collections import defaultdict

import pyrosimple

from pyrosimple.scripts.base import ScriptBaseWithConfig
from pyrosimple.util import rpc


class RtorrentMove(ScriptBaseWithConfig):
    """
    Move data actively seeded in rTorrent.
    """

    # argument description for the usage information
    ARGS_HELP = "<source>... <target>"

    # fields needed to find the item
    PREFETCH_FIELDS = [
        "d.hash",
        "d.name",
        "d.size_bytes",
        "d.directory",
        "d.complete",
        "d.is_multi_file",
    ]

    def add_options(self):
        """Add program options."""
        super().add_options()

        # basic options
        self.add_bool_option(
            "-n", "--dry-run", help="don't move data, just tell what would happen"
        )
        self.add_bool_option(
            "-F", "--force-incomplete", help="force a move of incomplete data"
        )
        self.parser.add_argument("source", nargs="+", help="source directories")
        self.parser.add_argument("target", help="target directory")

    def resolve_slashed(self, path):
        """Resolve symlinked directories if they end in a '/',
        remove trailing '/' otherwise.
        """
        if path.endswith(os.sep):
            path = path.rstrip(os.sep)
            if os.path.islink(path):
                real = os.path.realpath(path)
                self.log.debug('Resolved "%s/" to "%s"', path, real)
                path = real

        return path

    def guarded(self, call, *args):
        """Catch exceptions thrown by filesystem calls, and don't really
        execute them in dry-run mode.
        """
        self.log.debug("%s(%s)", call.__name__, ", ".join(args))
        if not self.options.dry_run:
            try:
                call(*args)
            except (OSError, UnicodeError) as exc:
                self.fatal(
                    "{}({}) failed [{}]".format(call.__name__, ", ".join(args), exc)
                )
        else:
            self.log.info("%s(%s)", call.__name__, ", ".join(args))

    def mainloop(self):
        """The main loop."""

        # TODO: Add mode to move tied metafiles, without losing the tie

        # Target handling
        target = self.options.target
        if "//" in target.rstrip("/"):
            # Create parts of target path
            existing, _ = target.split("//", 1)
            if not os.path.isdir(existing):
                self.fatal("Path before '//' MUST exists in %s", target)

            # Possibly create the rest
            target = target.replace("//", "/")
            if not os.path.exists(target):
                self.guarded(os.makedirs, target)

        # Preparation
        # TODO: Handle cases where target is the original download path correctly!
        #       i.e.   rtmv foo/ foo   AND   rtmv foo/ .   (in the download dir)
        proxy = pyrosimple.connect().open()
        download_path = os.path.realpath(
            os.path.expanduser(proxy.directory.default(rpc.NOHASH).rstrip(os.sep))
        )
        target = self.resolve_slashed(target)
        source_paths = [self.resolve_slashed(i) for i in self.options.source]
        source_realpaths = [os.path.realpath(i) for i in source_paths]
        source_items = defaultdict(list)  # map of source path to item
        items = list(pyrosimple.connect().items(prefetch=self.PREFETCH_FIELDS))

        # Validate source paths and find matching items
        for item in items:
            if not item.path:
                continue

            realpath = None
            try:
                realpath = os.path.realpath(item.path)
            except (OSError, UnicodeError) as exc:
                self.log.warning("Cannot realpath %r (%s)", item.path, exc)

            # Look if item matches a source path
            # TODO: Handle download items nested into each other!
            try:
                path_idx = source_realpaths.index(realpath or item.path)
            except ValueError:
                continue

            if realpath:
                self.log.debug("Item path %s resolved to %s", item.path, realpath)
            self.log.debug('Found "%s" for %s', item.name, source_paths[path_idx])
            source_items[source_paths[path_idx]].append(item)

        ##for path in source_paths: print path, "==>"; print "  " + "\n  ".join(i.path for i in source_items[path])

        if not os.path.isdir(target) and len(source_paths) > 1:
            self.fatal("Can't move multiple files to %s which is no directory!", target)

        # Actually move the data
        moved_count = 0
        for path in source_paths:
            item = None  # Make sure there's no accidental stale reference

            if not source_items[path]:
                self.log.warning("No download item found for %s, skipping!", path)
                continue

            if len(source_items[path]) > 1:
                self.log.warning(
                    "Can't handle multi-item moving yet, skipping %s!", path
                )
                continue

            if os.path.islink(path):
                self.log.warning("Won't move symlinks, skipping %s!", path)
                continue

            for item in source_items[path]:
                if os.path.islink(item.path) and os.path.realpath(
                    item.path
                ) != os.readlink(item.path):
                    self.log.warning(
                        "Can't handle multi-hop symlinks yet, skipping %s!", path
                    )
                    continue

                if not item.is_complete:
                    if self.options.force_incomplete:
                        self.log.warning("Moving incomplete item '%s'!", item.name)
                    else:
                        self.log.warning("Won't move incomplete item '%s'!", item.name)
                        continue

                moved_count += 1
                dst = target
                if os.path.isdir(dst):
                    dst = os.path.join(dst, os.path.basename(path))
                self.log.info("Moving to %s...", dst)

                # Pause torrent?
                # was_active = item.is_active and not self.options.dry_run
                # if was_active: item.pause()

                # TODO: move across devices
                # TODO: move using "d.directory.set" instead of symlinks
                if os.path.islink(item.path):
                    if os.path.abspath(dst) == os.path.abspath(
                        item.path.rstrip(os.sep)
                    ):
                        # Moving back to original place
                        self.log.debug("Unlinking %s", path)
                        self.guarded(os.remove, item.path)
                        self.guarded(os.rename, path, dst)
                    else:
                        # Moving to another place
                        self.log.debug("Re-linking %s", path)
                        self.guarded(os.rename, path, dst)
                        self.guarded(os.remove, item.path)
                        self.guarded(os.symlink, os.path.abspath(dst), item.path)
                else:
                    # Moving download initially
                    self.log.debug("Symlinking %s", path)
                    src1, src2 = os.path.join(
                        download_path, os.path.basename(item.path)
                    ), os.path.realpath(path)
                    assert src1 == src2, f"Item path {src1!r} should match {src2!r}!"
                    self.guarded(os.rename, item.path, dst)
                    self.guarded(os.symlink, os.path.abspath(dst), item.path)

                # Resume torrent?
                # if was_active: sitem.resume()

        # Print stats
        self.log.debug("RPC stats: %s", proxy)
        self.log.info(
            "Moved %d path%s (skipped %d)",
            moved_count,
            "" if moved_count == 1 else "s",
            len(source_paths) - moved_count,
        )


def run():  # pragma: no cover
    """The entry point."""
    RtorrentMove().run()


if __name__ == "__main__":
    run()
