import io
import os
import pipes
import socket
import subprocess
import time

from typing import Dict, Generator, List, Tuple, Union
from urllib import parse as urlparse
from urllib.error import URLError
from xmlrpc import client as xmlrpclib


def register_scheme(scheme):
    for method in filter(lambda s: s.startswith("uses_"), dir(urlparse)):
        getattr(urlparse, method).append(scheme)


class SCGIException(Exception):
    """SCGI protocol error"""


# Types of exceptions thrown
ERRORS = (SCGIException, URLError, xmlrpclib.Fault, socket.error)


#
# SCGI transports
#


class RTorrentTransport(xmlrpclib.Transport):
    def __init__(self, codec=xmlrpclib, *args, **kwargs):
        self.codec = codec
        super().__init__(*args, **kwargs)

    def parse_response(self, response):
        if self.codec == xmlrpclib:
            return super().parse_response(response)
        else:
            return self.codec.loads(response.read())


class TCPTransport(RTorrentTransport):
    CHUNK_SIZE: int = 32768
    """Transport via TCP socket."""

    def request(self, host, handler, request_body, verbose=False, headers={}):
        self.verbose = verbose
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            host, port = host.split(":")
            sock.connect((host, int(port)))
            sock.sendall(_encode_payload(request_body, headers.items()))
            with sock.makefile("rb") as handle:
                return self.parse_response(
                    io.BytesIO(_parse_response(handle.read())[0])
                )


class UnixTransport(xmlrpclib.Transport):
    """Transport via UNIX domain socket."""

    def request(self, host, handler, request_body, verbose=False):
        self.verbose = verbose
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(host)
            sock.sendall(_encode_payload(request_body))
            with sock.makefile("b") as handle:
                return self.parse_response(
                    io.BytesIO(_parse_response(handle.read())[0])
                )


class SSHTransport(xmlrpclib.Transport):
    pass


TRANSPORTS = {
    "scgi": TCPTransport,
    "scgi+unix": UnixTransport,
    "scgi+ssh": SSHTransport,
}

# Register our schemes to be parsed as having a netloc
for t in TRANSPORTS.keys():
    register_scheme(t)


def transport_from_url(url):
    """Create a transport for the given URL."""
    if "/" not in url and ":" in url and url.rsplit(":")[-1].isdigit():
        url = "scgi://" + url
    elif url.startswith("/"):
        url = "scgi+unix://"
    url = urlparse.urlsplit(
        url, scheme="scgi", allow_fragments=False
    )  # pylint: disable=redundant-keyword-arg

    try:
        transport = TRANSPORTS[url.scheme.lower()]
    except KeyError:
        # pylint: disable=raise-missing-from
        if not any((url.netloc, url.query)) and url.path.isdigit():
            # Support simplified "domain:port" URLs
            return transport_from_url("scgi://%s:%s" % (url.scheme, url.path))
        else:
            raise URLError("Unsupported scheme in URL %r" % url.geturl())
    else:
        return transport


#
# Helpers to handle SCGI data
# See spec at http://python.ca/scgi/protocol.txt
#


def _encode_netstring(data: bytes) -> bytes:
    "Encode data as netstring."
    return b"%d:%s," % (len(data), data)


def _encode_headers(headers: List[Tuple[str, str]]) -> bytes:
    "Make SCGI header bytes from list of tuples."
    return b"".join(
        [b"%s\0%s\0" % (k.encode("ascii"), v.encode("ascii")) for k, v in headers]
    )


def _encode_payload(data: bytes, headers=None) -> bytes:
    "Wrap data in an SCGI request."
    prolog: bytes = b"CONTENT_LENGTH\0%d\0SCGI\x001\0" % len(data)
    if headers:
        prolog += _encode_headers(headers)

    return _encode_netstring(prolog) + data


def _parse_headers(headers: bytes) -> Dict[str, str]:
    """
    Get headers dict from header bytestring.

    :param headers: An SCGI header bytestring
    :type headers: bytes
    :return: A dictionary of string keys/values
    """
    try:
        result = {}
        for line in headers.splitlines():
            if line:
                k, v = line.rstrip().split(b": ", 1)
                result[k.decode("ascii")] = v.decode("ascii")
        return result
    except (TypeError, ValueError) as exc:
        raise SCGIException(
            "Error in SCGI headers %r (%s)"
            % (
                headers.decode(),
                exc,
            )
        ) from exc


def _parse_response(resp: bytes) -> Tuple[bytes, Dict[str, str]]:
    """
    Get xmlrpc response from scgi response

    :param headers: An SCGI bytestring payload
    :type headers: bytes
    :return: A tuple of a binary payload and a dictionary of string keys/values
    """

    # Assume they care for standards and send us CRLF (not just LF)
    try:
        headers, payload = resp.split(b"\r\n\r\n", 1)
    except (TypeError, ValueError) as exc:
        raise SCGIException(
            "No header delimiter in SCGI response of length %d (%s)"
            % (
                len(resp),
                exc,
            )
        ) from exc
    parsed_headers = _parse_headers(headers)

    clen = parsed_headers.get("Content-Length")
    if clen is not None:
        # Check length, just in case the transport is bogus
        assert len(payload) == int(clen)

    return payload, parsed_headers
