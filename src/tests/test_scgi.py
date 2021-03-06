# pylint: disable=missing-docstring,too-few-public-methods
# pylint: disable=protected-access
""" SCGI tests.

    List of test cases taken from original BitTorrent code by Bram Cohen.

    Copyright (c) 2011-2020 The PyroScope Project <pyroscope.project@gmail.com>
"""
import socket
import time
import unittest

from urllib.error import URLError

import pytest

from pyrosimple.io import scgi


def test_bad_url():
    with pytest.raises(URLError):
        scgi.transport_from_url("xxxx:///")


@pytest.mark.parametrize(
    "url, transport",
    [
        ("scgi://localhost:5000/", scgi.TCPTransport),
        ("localhost:5000", scgi.TCPTransport),
        ("example.com:5000", scgi.TCPTransport),
        ("~/tmp/socket", scgi.UnixTransport),
        ("/tmp/socket", scgi.UnixTransport),
        ("scgi+unix:///tmp/socket", scgi.UnixTransport),
        ("scgi+unix:/tmp/socket", scgi.UnixTransport),
    ],
)
def test_local_transports(url, transport):
    assert scgi.transport_from_url(url) == transport


@pytest.mark.parametrize(
    "data, expected",
    [
        (b"", b"0:,"),
        (b"a", b"1:a,"),
        (b"aaaa", b"4:aaaa,"),
        # (b"\x20\xac", b"3:\xe2\x82\xac,"),
    ],
)
def test_encode_netstring(data, expected):
    assert scgi._encode_netstring(data) == expected


@pytest.mark.parametrize(
    "data, expected",
    [
        ((), b""),
        ((("a", "b"),), b"a\0b\0"),
        ((("a: 1", "b: 2"),), b"a: 1\0b: 2\0"),
    ],
)
def test_encode_headers(data, expected):
    assert scgi._encode_headers(data) == expected


@pytest.mark.parametrize(
    "data, headers, expected",
    [
        (
            b"",
            None,
            b"24:%s," % b"\0".join([b"CONTENT_LENGTH", b"0", b"SCGI", b"1", b""]),
        ),
        (
            b"*" * 10,
            None,
            b"25:%s," % b"\0".join([b"CONTENT_LENGTH", b"10", b"SCGI", b"1", b""])
            + b"*" * 10,
        ),
        (
            b"",
            [("a", "b")],
            b"28:%s,"
            % b"\0".join([b"CONTENT_LENGTH", b"0", b"SCGI", b"1", b"a", b"b", b""]),
        ),
    ],
)
def test_encode_payload(data, headers, expected):
    assert scgi._encode_payload(data, headers=headers) == expected


@pytest.mark.parametrize(
    "data, expected",
    [
        (b"", {}),
        (b"a: b\nc: d\n\n", dict(a="b", c="d")),
    ],
)
def test_parse_headers(data, expected):
    assert scgi._parse_headers(data) == expected


def test_bad_headers():
    bad_headers = b"a: b\nc; d\n\n"
    with pytest.raises(scgi.SCGIException):
        scgi._parse_headers(bad_headers)


def test_parse_response():
    data = b"Content-Length: 10\r\n\r\n" + b"*" * 10
    payload, headers = scgi._parse_response(data)

    assert payload == b"*" * 10
    assert headers == {"Content-Length": "10"}


def test_bad_response():
    bad_data = b"Content-Length: 10\n\n" + b"*" * 10
    with pytest.raises(scgi.SCGIException):
        scgi._parse_response(bad_data)
