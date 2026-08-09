"""Retry helpers for idempotent external HTTP reads."""

from __future__ import annotations

import http.client
import ssl
import time
import urllib.error
import urllib.request


ROUTE_ATTEMPTS = (
    ("direct", False),
    ("proxy", True),
    ("direct", False),
    ("proxy", True),
)
RETRY_DELAYS_SECONDS = (1, 5, 10)
RETRYABLE_HTTP_STATUSES = frozenset({429, 502, 503, 504})


def _build_opener(use_proxy: bool):
    proxy_handler = urllib.request.ProxyHandler() if use_proxy else urllib.request.ProxyHandler({})
    return urllib.request.build_opener(proxy_handler)


def read_url_with_retry(
    url: str,
    *,
    headers=None,
    timeout: float,
    method: str = "GET",
    consume=None,
):
    """Read an external URL using direct -> proxy -> direct -> proxy.

    A fresh request and opener are created for every attempt so proxy state cannot
    leak into a later direct attempt. Only transport failures and HTTP
    429/502/503/504 are retried; permanent HTTP failures are raised immediately.
    """
    if consume is None:
        consume = lambda response: response.read()

    last_error = None
    for attempt, (route_name, use_proxy) in enumerate(ROUTE_ATTEMPTS, start=1):
        try:
            request = urllib.request.Request(
                url,
                headers=dict(headers or {}),
                method=method,
            )
            response = _build_opener(use_proxy).open(request, timeout=timeout)
            try:
                return consume(response)
            finally:
                response.close()
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in RETRYABLE_HTTP_STATUSES or attempt == len(ROUTE_ATTEMPTS):
                raise
            error.close()
            failure = f"HTTP {error.code}"
        except (
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
            OSError,
            ssl.SSLError,
            http.client.HTTPException,
        ) as error:
            last_error = error
            if attempt == len(ROUTE_ATTEMPTS):
                raise
            failure = type(error).__name__

        print(
            f"[GPTImage2Prompt] request attempt {attempt}/4 via {route_name} "
            f"failed: {failure}"
        )
        time.sleep(RETRY_DELAYS_SECONDS[attempt - 1])

    raise last_error  # pragma: no cover
