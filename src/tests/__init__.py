# pylint: disable=
""" Unit Tests.

    Copyright (c) 2009, 2010 The PyroScope Project <pyroscope.project@gmail.com>
"""
import logging
import sys


TRACE = logging.DEBUG - 1


class TestLogger(logging.Logger):
    """A logger with trace()."""

    @classmethod
    def initialize(cls):
        """Register test logging."""
        logging.addLevelName(TRACE, "TRACE")
        logging.setLoggerClass(cls)

        if any(i in sys.argv for i in ("-v", "--verbose")):
            logging.getLogger().setLevel(TRACE)
        elif any(i in sys.argv for i in ("-q", "--quiet")):
            logging.getLogger().setLevel(logging.INFO)

    def trace(self, msg, *args, **kwargs):
        """Micro logging."""
        return self.log(TRACE, msg, *args, **kwargs)

    # FlexGet names
    debugall = trace
    verbose = logging.Logger.info


TestLogger.initialize()
