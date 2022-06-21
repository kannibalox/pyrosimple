# pylint: disable=
""" XMLRPC tests.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""
import logging
import unittest

import pytest

from pyrosimple.util import rpc


@pytest.mark.parametrize(
    "url",
    [
        "scgi://example.com:7000",
        "scgi:///var/tmp/rtorrent.sock",
        "http://example.com:7000",
        "http://example.com:7000?rpc=json",
        "http://example.com:7000/RPC3",
        "scgi+ssh://example.com:7000/RPC3",
    ],
)
def test_rpc_url(url):
    rpc.RTorrentProxy(url)
