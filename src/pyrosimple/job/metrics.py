"""Jobs for metric reporting"""
import pyrosimple

from pyrosimple import error
from pyrosimple.util import fmt, pymagic, rpc


class EngineStats:
    """Simple rTorrent connection statistics logger."""

    def __init__(self, config=None):
        """Set up statistics logger."""
        self.config = config or {}
        self.LOG = pymagic.get_class_logger(self)
        self.LOG.debug("Statistics logger created with config %r", self.config)
        self.engine = pyrosimple.connect()
        self.engine.open()

    def run(self):
        """Statistics logger job callback."""
        try:
            self.LOG.info(
                "Stats for %s - up %s, %s",
                self.engine.engine_id,
                fmt.human_duration(
                    self.engine.rpc.system.time() - self.engine.startup, 0, 2, True
                ).strip(),
                self.engine.rpc,
            )
        except (error.LoggableError, *rpc.ERRORS) as exc:
            self.LOG.warning(str(exc))
