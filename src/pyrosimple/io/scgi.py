"""Handles RPC methods over various transports"""
import io
import logging
import socket
import subprocess
import sys

from typing import Dict, List, Tuple, Type
from urllib import parse as urlparse
from urllib.error import URLError
from xmlrpc import client as xmlrpclib

from prometheus_client import Counter, Summary


request_counter = Counter(
    "transport_request", "Number of requests made by the transport"
)
request_size_counter = Counter("transport_request_size", "Size of the request in bytes")
response_time_summary = Summary("response_time", "Time spent watiing for a response")
response_size_counter = Counter(
    "transport_response_size", "Size of the response in bytes"
)

logger = logging.getLogger(__name__)


class SCGIException(Exception):
    """SCGI protocol error"""


# Types of exceptions thrown
ERRORS = (SCGIException, URLError, xmlrpclib.Fault, socket.error)


class RTorrentTransport(xmlrpclib.Transport):
    """Base class for handling transports. Primarily exists to allow
    using the different transports with different underlying RPC mechanisms"""

    def __init__(self, *args, url, codec=xmlrpclib, headers=(), **kwargs):
        if "/" not in url and ":" in url and url.rsplit(":")[-1].isdigit():
            url = "scgi://" + url
        if url.startswith("/") or url.startswith("~"):
            url = "scgi+unix://" + url
        self.url = url
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

    label = "ssh"

    def request(self, host, handler, request_body, verbose=False):
        request_counter.inc()
        request_size_counter.inc(len(request_body))
        self.verbose = verbose
        target = urlparse.urlparse(self.url).path
        cmd = ["ssh", host, "socat", "STDIO", target[1:]]
        with response_time_summary.time():
            resp = subprocess.run(
                cmd,
                input=_encode_payload(request_body, self._headers),
                capture_output=True,
                check=False,
            )
        if resp.returncode > 0:
            logger.error("SSH command returned non-zero exit code")
            logger.error("stderr: %s", resp.stderr)
            logger.error("stdout: %s", resp.stdout)
        response_size_counter.inc(len(resp.stdout))
        return self.parse_response(io.BytesIO(_parse_response(resp.stdout)[0]))


class HTTPTransport(RTorrentTransport):
    """Transport via HTTP(s) call."""

    # Notably the request here is *not* encoded into SCGI
    # since the web proxy handles that itself.
    def request(self, host, handler, request_body, verbose=False):
        # Defer loading for performance reasons
        import requests  # pylint: disable=import-outside-toplevel

        request_counter.inc()
        request_size_counter.inc(len(request_body))
        with response_time_summary.time():
            req = requests.post(
                self.url, headers=self._headers, data=request_body, timeout=60
            )
        response_size_counter.inc(len(req.content))
        req.raise_for_status()
        return self.parse_response(io.BytesIO(req.content))


class TCPTransport(RTorrentTransport):
    """Transport via TCP socket."""

    name = "tcp"

    def request(self, host, handler, request_body, verbose=False):
        request_counter.inc()
        request_size_counter.inc(len(request_body))
        self.verbose = verbose
        target = urlparse.urlparse(self.url)
        with response_time_summary.time():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                host, port = target.netloc.split(":")
                sock.connect((host, int(port)))
                sock.sendall(_encode_payload(request_body, self._headers))
                with sock.makefile("rb") as handle:
                    response = _parse_response(handle.read())[0]
        response_size_counter.inc(len(response))
        return self.parse_response(io.BytesIO(response))


class UnixTransport(RTorrentTransport):
    """Transport via UNIX domain socket."""

    def request(self, _host, handler, request_body, verbose=False):
        request_counter.inc()
        request_size_counter.inc(len(request_body))
        self.verbose = verbose
        target = urlparse.urlparse(self.url).path
        with response_time_summary.time():
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.connect(target)
                sock.sendall(_encode_payload(request_body))
                with sock.makefile("b") as handle:
                    response = _parse_response(handle.read())[0]
        response_size_counter.inc(len(response))
        return self.parse_response(io.BytesIO(response))


TRANSPORTS = {
    "scgi": TCPTransport,
    "http": HTTPTransport,
    "https": HTTPTransport,
    "scgi+unix": UnixTransport,
    "scgi+ssh": SSHTransport,
}


def register_scheme(scheme: str):
    """Helper method to register protocols with urllib"""
    for method in filter(lambda s: s.startswith("uses_"), dir(urlparse)):
        getattr(urlparse, method).append(scheme)


for t in TRANSPORTS:
    register_scheme(t)


def transport_from_url(url: str) -> Type[xmlrpclib.Transport]:
    """Create a transport for the given URL."""
    if "/" not in url and ":" in url and url.rsplit(":")[-1].isdigit():
        url = "scgi://" + url
    if url.startswith("/") or url.startswith("~"):
        url = "scgi+unix://" + url
    parsed_url = urlparse.urlsplit(url, allow_fragments=False)
    try:
        transport = TRANSPORTS[parsed_url.scheme.lower()]
        return transport
    except KeyError:
        # Support simplified "domain:port" URLs
        if not any((parsed_url.netloc, parsed_url.query)) and parsed_url.path.isdigit():
            return transport_from_url(f"scgi://{parsed_url.netloc}:{parsed_url.path}")
    raise URLError(f"Unsupported scheme in URL {parsed_url.geturl()!r}")


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
