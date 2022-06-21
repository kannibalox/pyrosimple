""" rTorrent Item Filter Jobs.

    Copyright (c) 2012 The PyroScope Project <pyroscope.project@gmail.com>
"""


from pyrosimple import error
from pyrosimple.util import pymagic, rpc


class FilterJobBase:
    """Base class for filter rule jobs."""

    def __init__(self, filter_config=None):
        """Set up filter config."""
        self.config = filter_config or {}
        self.LOG = pymagic.get_class_logger(self)
        self.LOG.debug(
            "%s created with config %r", self.__class__.__name__, self.config
        )

    def run(self):
        """Filter job callback."""

        try:
            # TODO: select view into items
            items = []
            self.run_filter(items)
        except (error.LoggableError, rpc.ERRORS) as exc:
            self.LOG.warning(str(exc))

    def run_filter(self, items):
        """Perform job on filtered items."""
        raise NotImplementedError()


class ActionRule(FilterJobBase):
    """Perform an action on selected items."""

    def run_filter(self, items):
        """Perform configured action on filtered items."""
        # TODO: what actions? rpc, delete, cull, stop, etc. for sure.


class TorrentMirror(FilterJobBase):
    """Mirror selected items via a specified tracker."""

    def run_filter(self, items):
        """Load filtered items into remote client via tracker / watchdir."""
        # TODO: config is tracker_url, tracker_upload, watch_dir
        # create clones of item's metafile, write to watch_dir, and upload
        # to tracker_upload (support file: at first, for a local bttrack);
        # also, already mirrored items have to be marked somehow
