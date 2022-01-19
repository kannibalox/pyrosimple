# -*- coding: utf-8 -*-
# pylint: disable=too-few-public-methods,no-else-return
""" XMLRPC via SCGI client proxy over various transports.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>

    Losely based on code Copyright (C) 2005-2007, Glenn Washburn <crass@berlios.de>
    SSH tunneling back-ported from https://github.com/Quantique
"""
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
import os
import time
import pipes
import socket
import subprocess

from urllib.error import URLError

from urllib import parse as urlparse
from xmlrpc import client as xmlrpclib


class SCGIException(Exception):
    """SCGI protocol error"""


# Types of exceptions thrown
ERRORS = (SCGIException, URLError, xmlrpclib.Fault, socket.error)


#
# SCGI transports
#


class LocalTransport(object):
    """Transport via TCP or a UNIX domain socket."""

    # Amount of bytes to read at once
    CHUNK_SIZE = 32768

    def __init__(self, url):
        self.url = url

        if url.netloc:
            # TCP socket
            addrinfo = list(
                set(
                    socket.getaddrinfo(
                        url.hostname, url.port, socket.AF_INET, socket.SOCK_STREAM
                    )
                )
            )
            if len(addrinfo) != 1:
                raise URLError(
                    "Host of URL %r resolves to multiple addresses %r"
                    % (url.geturl(), addrinfo)
                )

            self.sock_args = addrinfo[0][:3]
            self.sock_addr = addrinfo[0][4]
        else:
            # UNIX domain socket
            path = os.path.expanduser(url.path)
            self.sock_args = (socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock_addr = os.path.abspath(path)

    def send(self, data):
        """Open transport, send data, and yield response chunks."""
        sock = socket.socket(*self.sock_args)
        try:
            sock.connect(self.sock_addr)
        except socket.error as exc:
            raise socket.error("Can't connect to %r (%s)" % (self.url.geturl(), exc))

        try:
            # Send request
            sock.send(data)

            # Read response
            while True:
                chunk = sock.recv(self.CHUNK_SIZE)
                if chunk:
                    yield chunk
                else:
                    break
        finally:
            # Clean up
            sock.close()


class SSHTransport(object):
    """Transport via SSH to a UNIX domain socket."""

    def __init__(self, url):
        self.url = url
        self.cmd = ["ssh", "-T"]  # no pseudo-tty

        if not url.path.startswith("/"):
            raise URLError("Bad path in URL %r" % url.geturl())

        # pipes.quote is used because ssh always goes through a login shell.
        # The only exception is for redirecting ports, which can't be used
        # to access a domain socket.
        if url.path.startswith("/~/"):
            clean_path = "~/" + pipes.quote(url.path[3:])
        else:
            clean_path = pipes.quote(url.path)

        ssh_netloc = "".join(
            (url.username or "", "@" if url.username else "", url.hostname)
        )
        if url.port:
            reconstructed_netloc = "%s:%d" % (ssh_netloc, url.port)
            self.cmd.extend(["-p", str(url.port)])
        else:
            reconstructed_netloc = ssh_netloc
        if reconstructed_netloc != url.netloc:
            raise URLError(
                "Bad location in URL %r (expected %r)"
                % (url.geturl(), reconstructed_netloc)
            )

        self.cmd.extend(["--", ssh_netloc])
        # self.cmd.extend(["/bin/nc", "-U", "--", clean_path])
        self.cmd.extend(["socat", "STDIO", "UNIX-CONNECT:" + clean_path])

    def send(self, data):
        """Open transport, send data, and yield response chunks."""
        try:
            proc = subprocess.Popen(
                self.cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise URLError("Calling %r failed (%s)!" % (" ".join(self.cmd), exc))
        else:
            stdout, stderr = proc.communicate(data)
            if proc.returncode:
                raise URLError(
                    "Calling %r failed with RC=%d!\n%s"
                    % (
                        " ".join(self.cmd),
                        proc.returncode,
                        stderr,
                    )
                )
            yield stdout


TRANSPORTS = {
    "scgi": LocalTransport,
    "scgi+ssh": SSHTransport,
}

# Register our schemes to be parsed as having a netloc
urlparse.uses_netloc.extend(TRANSPORTS.keys())


def transport_from_url(url):
    """Create a transport for the given URL."""
    if "/" not in url and ":" in url and url.rsplit(":")[-1].isdigit():
        url = "scgi://" + url
    url = urlparse.urlsplit(
        url, scheme="scgi", allow_fragments=False
    )  # pylint: disable=redundant-keyword-arg

    try:
        transport = TRANSPORTS[url.scheme.lower()]
    except KeyError:
        if not any((url.netloc, url.query)) and url.path.isdigit():
            # Support simplified "domain:port" URLs
            return transport_from_url("scgi://%s:%s" % (url.scheme, url.path))
        else:
            raise URLError("Unsupported scheme in URL %r" % url.geturl())
    else:
        return transport(url)


#
# Helpers to handle SCGI data
# See spec at http://python.ca/scgi/protocol.txt
#


def _encode_netstring(data):
    "Encode data as netstring."
    return b"%d:%s," % (len(data), data)


def _encode_headers(headers):
    "Make SCGI header bytes from list of tuples."
    return b"".join(
        [b"%s\0%s\0" % (k.encode("ascii"), v.encode("ascii")) for k, v in headers]
    )


def _encode_payload(data, headers=None):
    "Wrap data in an SCGI request."
    prolog = b"CONTENT_LENGTH\0%d\0SCGI\x001\0" % len(data)
    if headers:
        prolog += _encode_headers(headers)

    return _encode_netstring(prolog) + data


def _parse_headers(headers):
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
        )


def _parse_response(resp):
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
        )
    headers = _parse_headers(headers)

    clen = headers.get("Content-Length")
    if clen is not None:
        # Check length, just in case the transport is bogus
        assert len(payload) == int(clen)

    return payload, headers


#
# SCGI request handling
#
class SCGIRequest(object):
    """Send a SCGI request.
    See spec at "http://python.ca/scgi/protocol.txt".

    Use tcp socket
    SCGIRequest('scgi://host:port').send(data)

    Or use the named unix domain socket
    SCGIRequest('scgi:///tmp/rtorrent.sock').send(data)
    """

    def __init__(self, url_or_transport):
        try:
            self.transport = transport_from_url(url_or_transport + "")
        except TypeError:
            self.transport = url_or_transport

        self.resp_headers = {}
        self.latency = 0.0

    def send(self, data):
        """Send data over scgi to URL and get response.

        :param data: The bytestring to send
        :type data: bytes
        :return: Response bytestring
        """
        start = time.time()
        try:
            scgi_resp = b"".join(self.transport.send(_encode_payload(data)))
        finally:
            self.latency = time.time() - start

        resp, self.resp_headers = _parse_response(scgi_resp)
        return resp


def scgi_request(url, methodname, *params, **kw):
    """Send a XMLRPC request over SCGI to the given URL.

    :param url: Endpoint URL.
    :param methodname: XMLRPC method name.
    :param params: Tuple of simple python objects.
    :type url: string
    :type methodname: string
    :keyword deserialize: Parse XML result? (default is True)
    :return: XMLRPC string response, or the equivalent Python data.
    """
    xmlreq = xmlrpclib.dumps(params, methodname)
    xmlresp = SCGIRequest(url).send(xmlreq.encode()).decode()

    if kw.get("deserialize", True):
        # This fixes a bug with the Python xmlrpclib module
        # (has no handler for <i8> in some versions)
        xmlresp = xmlresp.replace("<i8>", "<i4>").replace("</i8>", "</i4>")

        # Return deserialized data
        return xmlrpclib.loads(xmlresp)[0][0]
    else:
        # Return raw XML
        return xmlresp
