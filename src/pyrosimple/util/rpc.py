""" RTorrent client proxy.

    Copyright (c) 2011 The PyroScope Project <pyroscope.project@gmail.com>
"""


import base64
import functools
import json
import logging
import random
import urllib
import warnings

from typing import Any, Dict, List, Tuple, cast
from xmlrpc import client as xmlrpclib

from pyrosimple.io import scgi


logger = logging.getLogger(__name__)

NOHASH = (
    ""  # use named constant to make new-syntax commands with no hash easily searchable
)


class JSONRPCEncoder(json.JSONEncoder):
    """Encode xmlrpc.Binary data in a format jesec/rtorrent
    expects. The necessary command logic when handling load vs
    load.raw still needs to be handled separately."""

    def default(self, o):
        if isinstance(o, xmlrpclib.Binary):
            return "data:base64," + base64.b64encode(o.data).decode("ascii")
        return json.JSONEncoder.default(self, o)


CACHE_METHOD = {
    "d.chunk_size",
    "d.is_private",
    "d.name",
    "d.size_bytes",
    "d.size_chunks",
    "d.size_files",
    "system.api_version",
    "system.client_version",
    "system.library_version",
}


class RpcError(xmlrpclib.Fault):
    """Base class for XMLRPC protocol errors."""

    def __init__(self, faultString: str, faultCode: int = -500):
        super().__init__(faultCode, faultString)


class HashNotFound(RpcError):
    """Non-existing or disappeared hash."""

    def __init__(self, faultString: str, faultCode: int = -404):
        super().__init__(faultString, faultCode)


ERRORS = (RpcError,) + scgi.ERRORS


class RTorrentProxy(xmlrpclib.ServerProxy):
    # pylint: disable=super-init-not-called
    """Proxy to rTorrent's RPC interface.

    Method calls are built from attribute accesses, i.e. you can do
    something like `proxy.system.client_version()`.

    All methods from ServerProxy are being overridden due to the combination
    of self.__var name mangling and the __call__/__getattr__ magic.
    """

    def __init__(
        self,
        url,
        transport=None,
        encoding=None,
        verbose=False,
        allow_none=False,
        use_datetime=False,
        use_builtin_types=False,
        *,
        headers=(),
        context=None,
    ):
        # Get the url
        parsed_url = urllib.parse.urlsplit(url)
        queries = urllib.parse.parse_qs(parsed_url.query)
        # Config the connection details
        self.__rpc_codec = queries.get("rpc", ["xml"])[0]
        self.__url = url
        self.__host = parsed_url.netloc
        self.__handler = urllib.parse.urlunsplit(["", "", *parsed_url[2:]])
        # The /RPC2 convention just comes from the xmlrpc CLI tool, but is
        # generally used during ruTorrent setups
        if not self.__handler and parsed_url.scheme in ("http", "https"):
            warnings.warn(
                "Automatically adding '/RPC2' to the end of URLs is deprecated and will be removed in a future release."
                f"To fix this warning, change the connection URL to '{url}/RPC2'",
                stacklevel=2,
            )
            self.__handler = "/RPC2"
            self.__url += "/RPC2"

        if transport is None:
            if self.__rpc_codec == "json":
                codec = json
                headers = [("CONTENT_TYPE", "application/json")]
            elif self.__rpc_codec == "xml":
                codec = xmlrpclib
            handler = scgi.transport_from_url(url)
            transport = handler(
                url=self.__url,
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

    def __request_xml(self, methodname: str, params: Tuple[Any]):
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
            return response[0]
        return response

    def __batch_request_json(self, calls: List) -> List:
        """Handle multicalls in place of XMLRPC's built-in
        system.multilcall."""
        batch_call: List[Dict] = [
            {
                "jsonrpc": "2.0",
                "method": call["methodName"],
                "params": call["params"] or [""],
                "id": index,
            }
            for index, call in enumerate(calls)
        ]
        request: bytes = json.dumps(batch_call).encode(
            self.__encoding, "xmlcharrefreplace"
        )
        response: Tuple[Dict] = cast(
            Tuple[Dict],
            self.__transport.request(
                self.__host,
                self.__handler,
                request,
                verbose=self.__verbose,
            ),
        )

        def sort_key(i: Dict) -> int:
            return int(i["id"])

        result = [[r["result"]] for r in sorted(response, key=sort_key)]
        return result

    def __request_json(self, methodname, params):
        if not params:
            params = [""]

        # system.multicall isn't defined by the app,
        # but by the xmlrpc library, so we intercept it
        # and turn it into a batch request
        if methodname == "system.multicall":
            return self.__batch_request_json(params[0])

        # This random ID feels silly but there's not much need for anything better at the moment
        # since the RPC interface is synchronous.
        rpc_id = random.randint(0, 100)
        request = (
            JSONRPCEncoder(separators=(",", ":"))
            .encode(
                {
                    "params": params,
                    "method": methodname,
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                }
            )
            .encode(self.__encoding, "xmlcharrefreplace")
        )
        if self.__verbose:
            print("req: ", request)

        response: Dict = self.__transport.request(
            self.__host,
            self.__handler,
            request,
            verbose=self.__verbose,
        )

        if response["id"] != rpc_id:
            raise ValueError(
                f"RPC IDs do not match: sent={rpc_id} received={response['id']}"
            )
        if "error" in response:
            if "message" in response["error"]:
                if (
                    response["error"]["message"]
                    == "invalid parameters: info-hash not found"
                ):
                    raise HashNotFound(str(response["error"]))
                if "code" in response["error"]:
                    raise RpcError(
                        response["error"]["message"], response["error"]["code"]
                    )
            raise RpcError(f"Received error: {response['error']}")
        if "result" not in response:
            raise ValueError(f"Result not found in response: {response}")
        return response["result"]

    def __request(self, methodname, params):
        """Determines whether or not a request should be cached,
        then passes it to the appropriate method"""
        if methodname in CACHE_METHOD:
            return self.__cached_request(methodname, params)
        return self.__request_switch(methodname, params)

    @functools.lru_cache(maxsize=32)
    def __cached_request(self, methodname, params):
        """Simpled cache pass-through method to more easily take advantage of functools.lru_cache"""
        return self.__request_switch(methodname, params)

    def __request_switch(self, methodname, params):
        """Determines whether the request should go through
        xml or json and calls the appropriate method."""
        logger.debug("method '%s', params %s", methodname, params)
        try:
            if self.__rpc_codec == "xml":
                return self.__request_xml(methodname, params)
            if self.__rpc_codec == "json":
                return self.__request_json(methodname, params)
        except xmlrpclib.Fault as exc:
            if exc.faultString == "Could not find info-hash.":
                raise HashNotFound(  # pylint: disable=raise-missing-from
                    exc.faultString
                )
            raise exc
        raise ValueError(f"Invalid RPC protocol '{self.__rpc_codec}'")

    def __repr__(self):
        return f"<{self.__class__.__name__} via {self.__rpc_codec} for {self.__url}>"

    def __getattr__(self, name):
        # magic method dispatcher
        # Hardcode the most useful alias
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
