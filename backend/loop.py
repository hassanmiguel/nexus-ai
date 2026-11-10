"""Event-loop factory tuned for NEXUS on Windows.

CPython's default Windows event loop is the Proactor loop. Its accept path
uses AcceptEx and, under connection resets, an internal future can finish with
``WinError 64`` without ever being awaited, which asyncio then prints as:

    Task exception was never retrieved
    ...
    Accept failed on a socket

The Selector loop uses a plain non-blocking ``accept()`` and simply retries on
transient connection aborts. NEXUS never spawns asyncio subprocesses (it runs
subprocesses through ``subprocess.run`` in worker threads), so the Selector
loop is a drop-in replacement on Windows.

On every other platform this keeps the stock default loop.
"""
from __future__ import annotations

import asyncio
import errno
import os
import sys

_BENIGN_NETWORK_ERRNOS = {
    109, 232, 233,  # Windows: broken pipe, pipe closing, pipe connected
    995, 10038, 10053, 10054, 10058, 10060,  # Windows socket aborts/timeouts
}
_BENIGN_ERRNO_NAMES = {
    errno.ECONNRESET, errno.ECONNABORTED, errno.EPIPE, errno.ETIMEDOUT,
    errno.ENETRESET, errno.ENETDOWN, errno.ECONNREFUSED,
}


def _is_benign_network_error(exc: BaseException | None) -> bool:
    if not isinstance(exc, OSError):
        return False
    if exc.errno in _BENIGN_ERRNO_NAMES or exc.errno in _BENIGN_NETWORK_ERRNOS:
        return True
    winerror = getattr(exc, 'winerror', None)
    return winerror in _BENIGN_NETWORK_ERRNOS or winerror == 64


def install_exception_handler(loop: asyncio.AbstractEventLoop | None = None, verbose_env: str = 'NEXUS_VERBOSE_NETWORK') -> None:
    """Install a custom event loop exception handler that suppresses benign connection-reset tracebacks."""
    try:
        loop = loop or asyncio.get_running_loop()
    except RuntimeError:
        return
    previous = loop.get_exception_handler()
    if os.environ.get(verbose_env) == '1':
        return

    def handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
        message = str(context.get('message') or '')
        exc = context.get('exception')
        lower_msg = message.lower()
        if ('accept failed' in lower_msg or 'exception was never retrieved' in lower_msg) and _is_benign_network_error(exc):
            return
        if previous is not None:
            previous(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(handler)


def selector_loop_factory(use_subprocess: bool = False):
    """Return a fresh event loop for uvicorn's ``loop=`` setting.

    When a custom loop string is configured, uvicorn treats the imported
    callable itself as the loop factory and calls it with no arguments, so this
    function must return an *instance* (not another factory and not a class).
    """
    if sys.platform == 'win32' and not use_subprocess:
        return asyncio.SelectorEventLoop()
    if sys.platform == 'win32':
        return asyncio.ProactorEventLoop()
    return asyncio.SelectorEventLoop()
