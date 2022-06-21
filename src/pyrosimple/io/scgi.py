"""Handles RPC methods over various transports"""
import io
import logging
import socket
import subprocess
import sys
import urllib.request

from typing import Dict, List, Tuple, Type
from urllib import parse as urlparse
from urllib.error import URLError
from xmlrpc import client as xmlrpclib


logger = logging.getLogger(__name__)


def register_scheme(scheme: str):
    """Helper method to register protocols with urllib"""
    for method in filter(lambda s: s.startswith("uses_"), dir(urlparse)):
        getattr(urlparse, method).append(scheme)


class SCGIException(Exception):
    """SCGI protocol error"""


# Types of exceptions thrown
ERRORS = (SCGIException, URLError, xmlrpclib.Fault, socket.error)


class RTorrentTransport(xmlrpclib.Transport):
    """Base class for handle transports. Primarily exists to allow
    using the same transport with a different underlying RPC mechanism"""

    def __init__(self, *args, uri, codec=xmlrpclib, headers=(), **kwargs):
        self.uri = uri
        self.codec = codec
        self.verbose = False
        # We need to handle the headers differently based on the RPC protocols
        self._headers = list(headers)
        # Pass them to the transport in py 3.8+ only
        if sys.version_info.minor >= 8:
            kwargs["headers"] = self._headers
        super().__init__(*args, **kwargs)

    def parse_response(self, response):
        if self.codec == xmlrpclib:
            return super().parse_response(response)
        return self.codec.loads(response.read())


class SSHTransport(RTorrentTransport):
    """Transport via SSH conneection."""

    def request(self, host, handler, request_body, verbose=False):
        self.verbose = verbose
        target = urlparse.urlparse(self.uri).path
        cmd = ["ssh", host, "socat", "STDIO", target[1:]]
        resp = subprocess.run(
            cmd,
            input=_encode_payload(request_body, self._headers),
            capture_output=True,
            check=False,
        )
        if resp.returncode > 0:
            print("SSH command returned non-zero exit code")
            print("stderr:", resp.stderr)
            print("stdout:", resp.stdout)
        return self.parse_response(io.BytesIO(_parse_response(resp.stdout)[0]))


class HTTPTransport(RTorrentTransport):
    """Transport via HTTP(s) call."""

    def request(self, host, handler, request_body, verbose=False):
        self.verbose = verbose
        req = urllib.request.Request(self.uri)
        for key, val in self._headers:
            req.add_header(key, val)
        req.data = request_body
        with urllib.request.urlopen(req) as resp:
            return self.parse_response(resp)


class TCPTransport(RTorrentTransport):
    """Transport via TCP socket."""

    def request(self, host, handler, request_body, verbose=False):
        self.verbose = verbose
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            host, port = host.split(":")
            sock.connect((host, int(port)))
            sock.sendall(_encode_payload(request_body, self._headers))
            with sock.makefile("rb") as handle:
                return self.parse_response(
                    io.BytesIO(_parse_response(handle.read())[0])
                )


class UnixTransport(RTorrentTransport):
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


TRANSPORTS = {
    "scgi": TCPTransport,
    "http": HTTPTransport,
    "https": HTTPTransport,
    "scgi+unix": UnixTransport,
    "scgi+ssh": SSHTransport,
}


for t in TRANSPORTS:
    register_scheme(t)


def transport_from_url(url: str) -> Type[xmlrpclib.Transport]:
    """Create a transport for the given URL."""
    if "/" not in url and ":" in url and url.rsplit(":")[-1].isdigit():
        url = "scgi://" + url
    elif url.startswith("/") or url.startswith("~"):
        url = "scgi+unix://"
    parsed_url = urlparse.urlsplit(url, scheme="scgi", allow_fragments=False)

    try:
        transport = TRANSPORTS[parsed_url.scheme.lower()]
    except KeyError:
        # pylint: disable=raise-missing-from
        if not any((parsed_url.netloc, parsed_url.query)) and parsed_url.path.isdigit():
            # Support simplified "domain:port" URLs
            return transport_from_url(f"scgi://{parsed_url.scheme}:{parsed_url.path}")
        raise URLError(f"Unsupported scheme in URL {parsed_url.geturl()}")
    return transport


def _encode_netstring(data: bytes) -> bytes:
    "Encode data as netstring."
    return b"%d:%s," % (len(data), data)


def _encode_headers(headers: List[Tuple[str, str]]) -> bytes:
    "Make SCGI header bytes from list of tuples."
    return b"".join(
        [b"%s\0%s\0" % (k.encode("ascii"), v.encode("ascii")) for k, v in headers]
    )


def _encode_payload(data: bytes, headers: List[Tuple[str, str]] = None) -> bytes:
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
                key, value = line.rstrip().split(b": ", 1)
                result[key.decode("ascii")] = value.decode("ascii")
        return result
    except (TypeError, ValueError) as exc:
        raise SCGIException(f"Error in SCGI headers {headers.decode()}") from exc


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
            f"No header delimiter in SCGI response of length {len(resp)}"
        ) from exc
    parsed_headers = _parse_headers(headers)

    clen = parsed_headers.get("Content-Length")
    if clen is not None:
        # Check length, just in case the transport is bogus
        assert len(payload) == int(clen)

    return payload, parsed_headers
