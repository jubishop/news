"""Fake DNS and routing for the page browser's tests, loaded through PYTHONPATH.

Names under .test resolve to a public address, and connections to that address
reach the local test origin instead, so the browser's proxy runs unchanged.
"""

import asyncio
import socket

PUBLIC = "93.184.215.14"
_getaddrinfo = socket.getaddrinfo
_open_connection = asyncio.open_connection


def getaddrinfo(host, port, *args, **kwargs):
    return _getaddrinfo(PUBLIC if isinstance(host, str) and host.endswith(".test") else host, port, *args, **kwargs)


async def open_connection(host=None, port=None, *args, **kwargs):
    return await _open_connection("127.0.0.1" if host == PUBLIC else host, port, *args, **kwargs)


socket.getaddrinfo = getaddrinfo
asyncio.open_connection = open_connection
