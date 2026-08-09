import ssl
import urllib.error
import urllib.request
from unittest import mock

import pytest

from http_retry import ROUTE_ATTEMPTS, read_url_with_retry


def test_transport_failures_run_all_four_routes(monkeypatch):
    proxy_maps = []
    opener = mock.Mock()
    opener.open.side_effect = [
        urllib.error.URLError("offline"),
        TimeoutError("timed out"),
        ConnectionError("reset"),
        mock.Mock(read=lambda: b"ok"),
    ]

    monkeypatch.setattr(
        urllib.request,
        "ProxyHandler",
        lambda proxies=None: proxy_maps.append(proxies) or mock.Mock(),
    )
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_: opener)
    sleep = mock.Mock()
    monkeypatch.setattr("http_retry.time.sleep", sleep)

    assert read_url_with_retry("https://example.com", timeout=3) == b"ok"
    assert ROUTE_ATTEMPTS == (
        ("direct", False),
        ("proxy", True),
        ("direct", False),
        ("proxy", True),
    )
    assert proxy_maps == [{}, None, {}, None]
    assert [call.args[0] for call in sleep.call_args_list] == [1, 5, 10]


@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_temporary_http_status_is_retried(monkeypatch, status):
    error = urllib.error.HTTPError("https://example.com", status, "temporary", {}, None)
    response = mock.Mock(read=lambda: b"ok")
    opener = mock.Mock()
    opener.open.side_effect = [error, response]
    monkeypatch.setattr("http_retry._build_opener", lambda *_: opener)
    monkeypatch.setattr("http_retry.time.sleep", mock.Mock())

    assert read_url_with_retry("https://example.com", timeout=3) == b"ok"
    assert opener.open.call_count == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500])
def test_permanent_http_status_is_not_retried(monkeypatch, status):
    error = urllib.error.HTTPError("https://example.com", status, "permanent", {}, None)
    opener = mock.Mock()
    opener.open.side_effect = error
    monkeypatch.setattr("http_retry._build_opener", lambda *_: opener)

    with pytest.raises(urllib.error.HTTPError):
        read_url_with_retry("https://example.com", timeout=3)

    assert opener.open.call_count == 1


def test_tls_eof_while_reading_uses_next_route(monkeypatch):
    first = mock.Mock()
    first.read.side_effect = ssl.SSLEOFError(
        8, "EOF occurred in violation of protocol"
    )
    second = mock.Mock(read=lambda: b"complete")
    opener = mock.Mock()
    opener.open.side_effect = [first, second]
    monkeypatch.setattr("http_retry._build_opener", lambda *_: opener)
    sleep = mock.Mock()
    monkeypatch.setattr("http_retry.time.sleep", sleep)

    assert read_url_with_retry("https://example.com", timeout=3) == b"complete"
    assert opener.open.call_count == 2
    sleep.assert_called_once_with(1)
    first.close.assert_called_once()
    second.close.assert_called_once()
