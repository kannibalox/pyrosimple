""" Logging Support.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import logging


def get_logfile(logger=None):
    """Return log file of first file handler associated with the (root) logger.
    None if no such handler is found.
    """
    logger = logger or logging.getLogger()
    handlers = [i for i in logger.handlers if isinstance(i, logging.FileHandler)]
    return handlers[0].baseFilename if handlers else None
