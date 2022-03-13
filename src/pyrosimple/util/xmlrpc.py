# -*- coding: utf-8 -*-
""" RTorrent client proxy.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
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

import json
import random
import urllib

from xmlrpc import client as xmlrpclib

from pyrosimple.io import scgi


NOHASH = (
    ""  # use named constant to make new-syntax commands with no hash easily searchable
)


class XmlRpcError(Exception):
    """Base class for XMLRPC protocol errors."""

    def __init__(self, msg, *args):
        Exception.__init__(self, msg, *args)
        self.message = msg.format(*args)
        self.faultString = self.message
        self.faultCode = -500

    def __str__(self):
        return self.message


class HashNotFound(XmlRpcError):
    """Non-existing or disappeared hash."""

    def __init__(self, msg, *args):
        XmlRpcError.__init__(self, msg, *args)
        self.faultCode = -404


# Currently, we don't have our own errors, so just copy it
ERRORS = (XmlRpcError,) + scgi.ERRORS


class RTorrentProxy(xmlrpclib.ServerProxy):
    # pylint: disable=super-init-not-called
    """Proxy to rTorrent's RPC interface.

    Method calls are built from attribute accesses, i.e. you can do
    something like C{proxy.system.client_version()}.

    All methods from ServerProxy are being overridden due to the combination
    of self.__var name mangling and the __call__/__getattr__ magic.
    """

    def __init__(
        self,
        uri,
        transport=None,
        encoding=None,
        verbose=False,
        allow_none=False,
        use_datetime=False,
        use_builtin_types=False,
        *,
        headers=(),
        context=None,
    ):  # pylint: disable=unused-argument
        # establish a "logical" server connection

        # get the url
        p = urllib.parse.urlsplit(uri)
        q = urllib.parse.parse_qs(p.query)
        if p.scheme not in ("http", "https", "scgi", "scgi+ssh", "scgi+unix"):
            raise OSError("unsupported XML-RPC protocol")
        if "rpc" in q:
            self.__rpc_codec = q["rpc"][0]
        else:
            self.__rpc_codec = "xml"
        self.__uri = uri
        self.__host = p.netloc
        self.__handler = urllib.parse.urlunsplit(["", "", *p[2:]])
        if not self.__handler:
            if p.scheme in ("http", "https"):
                self.__handler = "/RPC2"
            else:
                self.__handler = ""

        if transport is None:
            if self.__rpc_codec == "json":
                codec = json
                headers = [("CONTENT_TYPE", "application/json")]
            elif self.__rpc_codec == "xml":
                codec = xmlrpclib
            handler = scgi.transport_from_url(uri)
            transport = handler(
                use_datetime=use_datetime,
                use_builtin_types=use_builtin_types,
                codec=codec,
                headers=headers,
            )
        self.__transport = transport
        self.__encoding = encoding or "utf-8"
        self.__verbose = verbose
        self.__allow_none = allow_none

    def __close(self):
        self.__transport.close()

    def __request_xml(self, methodname, params):
        # Verbatim from parent method
        request = xmlrpclib.dumps(
            params,
            methodname,
            encoding=self.__encoding,
            allow_none=self.__allow_none,
        ).encode(self.__encoding, "xmlcharrefreplace")
        if self.__verbose:
            print("req: ", request)

        response = self.__transport.request(
            self.__host, self.__handler, request, verbose=self.__verbose
        )

        if len(response) == 1:
            response = response[0]

        return response

    def __request_json(self, methodname, params):
        if not params:
            params = [""]

        # This feels silly but there's not much need for anything better ATM.
        rpc_id = random.randint(0, 100)
        request = json.dumps(
            {
                "params": params,
                "method": methodname,
                "jsonrpc": "2.0",
                "id": rpc_id,
            }
        ).encode(self.__encoding, "xmlcharrefreplace")
        if self.__verbose:
            print("req: ", request)

        response = self.__transport.request(
            self.__host,
            self.__handler,
            request,
            verbose=self.__verbose,
        )

        if response["id"] != rpc_id:
            raise ValueError(f"RPC IDs {rpc_id} and {response['id']} do not match")
        if "error" in response:
            raise ValueError(f"Received error: {response['error']}")
        return response["result"]

    def __request(self, methodname, params):
        # call a method on the remote server
        try:
            if self.__rpc_codec == "xml":
                return self.__request_xml(methodname, params)
            if self.__rpc_codec == "json":
                return self.__request_json(methodname, params)
        except xmlrpclib.Fault as exc:
            if exc.faultString == "Could not find info-hash.":
                raise HashNotFound(exc.faultString) # pylint: disable=raise-missing-from
            raise exc
        raise ValueError(f"Invalid RPC protocol '{self.__rpc_codec}'")

    def __repr__(self):
        return f"<{self.__class__.__name__} via {self.__rpc_codec} for {self.__uri}>"

    def __getattr__(self, name):
        # magic method dispatcher
        if name == "log":
            name = "print"
        return xmlrpclib._Method(self.__request, name)

    # note: to call a remote object with a non-standard name, use
    # result getattr(server, "strange-python-name")(args)

    def __call__(self, attr):
        """A workaround to get special attributes on the ServerProxy
        without interfering with the magic __getattr__
        """
        if attr == "close":
            return self.__close
        if attr == "transport":
            return self.__transport
        raise AttributeError(f"Attribute {attr} not found")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.__close()
