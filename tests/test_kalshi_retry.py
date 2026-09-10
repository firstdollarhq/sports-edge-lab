"""Retry behaviour for the Kalshi client.

This runs unattended on a schedule, and paginating several series back-to-back
reliably trips the rate limiter, so a 429 must cost a pause rather than the run.
"""
import pytest
import requests

from sportsedge.ingest import kalshi


class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {"markets": []}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(kalshi.time, "sleep", lambda _s: None)


def test_retries_then_succeeds(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _Resp(429) if len(calls) < 3 else _Resp(200, {"ok": True})

    monkeypatch.setattr(kalshi.requests, "get", fake_get)
    assert kalshi._get("/markets") == {"ok": True}
    assert len(calls) == 3


def test_gives_up_after_max_retries(monkeypatch):
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _Resp(429)

    monkeypatch.setattr(kalshi.requests, "get", fake_get)
    with pytest.raises(requests.HTTPError):
        kalshi._get("/markets")
    assert len(calls) == kalshi.MAX_RETRIES


def test_client_error_is_not_retried(monkeypatch):
    """A 404 is a bug in our request; retrying just wastes the rate limit."""
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return _Resp(404)

    monkeypatch.setattr(kalshi.requests, "get", fake_get)
    with pytest.raises(requests.HTTPError):
        kalshi._get("/markets")
    assert len(calls) == 1
