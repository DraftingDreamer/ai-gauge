import pytest
from datetime import datetime, timedelta, timezone

from aigauge.models import SnapshotStatus
from aigauge.providers._resets_common import (
    ResetEvent,
    ResetsProviderBase,
    build_snapshot,
    relative_age,
)

NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


def _event() -> ResetEvent:
    return ResetEvent(
        kind="landed", id="event-1", at=NOW - timedelta(hours=2),
        summary="limits refilled", detail="A detailed synthetic announcement.",
        url="https://example.test/event-1",
    )


def test_relative_age_boundaries_and_future():
    assert relative_age(NOW - timedelta(seconds=59), NOW) == "just now"
    assert relative_age(NOW - timedelta(minutes=59), NOW) == "59m ago"
    assert relative_age(NOW - timedelta(hours=23), NOW) == "23h ago"
    assert relative_age(NOW - timedelta(days=1), NOW) == "1d ago"
    assert relative_age(NOW + timedelta(days=1), NOW) == "just now"


def test_build_snapshot_formats_plain_text_row_and_safe_raw_data():
    event = _event()
    snapshot = build_snapshot("codex_resets", event, None, NOW)
    assert snapshot.status == SnapshotStatus.OK
    assert len(snapshot.metrics) == 1
    metric = snapshot.metrics[0]
    assert metric.label == "Reset · limits refilled, 2h ago"
    assert " · " in metric.label
    assert metric.percent_used is None
    assert metric.resets_at is None
    assert metric.window is None
    assert metric.reset_label is None
    assert metric.note == event.detail
    assert event.detail not in str(snapshot.raw)
    assert snapshot.raw == {
        "event_key": "landed:event-1", "event_kind": "landed",
        "event_url": event.url, "provisional": False, "dismissed": False,
    }
    assert snapshot.fetched_at == NOW.astimezone().replace(tzinfo=None)
    assert snapshot.fetched_at.tzinfo is None


def test_build_snapshot_hides_dismissed_event_and_keeps_error_event():
    event = _event()
    dismissed = build_snapshot("codex_resets", event, event.key, NOW)
    failed = build_snapshot("codex_resets", event, None, NOW, error="HTTP 503")
    assert dismissed.metrics == []
    assert dismissed.raw["dismissed"] is True
    assert failed.status == SnapshotStatus.ERROR
    assert failed.error == "HTTP 503"
    assert len(failed.metrics) == 1
    assert failed.metrics[0].label.startswith("Reset ·")


class _FakeResetsProvider(ResetsProviderBase):
    name = "fake_resets"
    display_name = "Fake Resets"

    def __init__(self, clock):
        super().__init__(clock=clock)
        self.calls = 0

    def _fetch_latest_event(self):
        self.calls += 1
        return _event()


def test_refresh_throttles_successful_requests_for_15_minutes(monkeypatch):
    current = [NOW]
    provider = _FakeResetsProvider(clock=lambda: current[0])
    monkeypatch.setattr(provider, "_run_async", lambda work, on_done: on_done(work()))
    snapshots = []
    provider.refresh(snapshots.append)
    current[0] += timedelta(minutes=14, seconds=59)
    provider.refresh(snapshots.append)
    assert provider.calls == 1
    assert len(snapshots) == 2
    assert snapshots[1].status == SnapshotStatus.OK
    current[0] += timedelta(seconds=1)
    provider.refresh(snapshots.append)
    assert provider.calls == 2


import json
from pathlib import Path
import responses
from aigauge.providers.codex_resets import CODEX_RESETS_URL, CodexResetsProvider

FIXTURES = Path(__file__).parent / "fixtures" / "resets"

def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

def _sync(provider, monkeypatch):
    monkeypatch.setattr(provider, "_run_async", lambda work, on_done: on_done(work()))

@pytest.mark.parametrize(
    "url",
    [
        "ms-msdt:/id PCWDiagnostic",
        "file:///C:/Windows/win.ini",
        "javascript:alert(1)",
        "https:///nohost",
        "",
    ],
)
def test_reset_event_rejects_non_http_urls(url):
    event = ResetEvent("landed", "1", NOW, "summary", "detail", url)
    assert event.url is None

@pytest.mark.parametrize("url", ["https://x.example/p", "HTTPS://X.EXAMPLE/p"])
def test_reset_event_accepts_http_urls(url):
    assert ResetEvent("landed", "1", NOW, "summary", "detail", url).url == url

@responses.activate
def test_failed_fetches_back_off_for_15_minutes_even_after_success(monkeypatch):
    current = [NOW]
    provider = CodexResetsProvider(clock=lambda: current[0])
    _sync(provider, monkeypatch)
    responses.add(responses.GET, CODEX_RESETS_URL, json=_fixture("codex_status.json"), status=200)
    for _ in range(2):
        responses.add(responses.GET, CODEX_RESETS_URL, status=503)
    provider.refresh(lambda snapshot: None)
    current[0] += timedelta(minutes=15)
    provider.refresh(lambda snapshot: None)
    assert len(responses.calls) == 2
    for _ in range(14):
        current[0] += timedelta(minutes=1)
        provider.refresh(lambda snapshot: None)
    assert len(responses.calls) == 2
    current[0] += timedelta(minutes=1)
    provider.refresh(lambda snapshot: None)
    assert len(responses.calls) == 3

@pytest.mark.parametrize(("retry_after", "blocked", "advance"), [
    ("3600", timedelta(minutes=59, seconds=59), timedelta(seconds=1)),
    ("0", timedelta(minutes=14, seconds=59), timedelta(seconds=1)),
])
@responses.activate
def test_retry_after_is_a_minimum_15_minute_backoff(monkeypatch, retry_after, blocked, advance):
    current = [NOW]
    provider = CodexResetsProvider(clock=lambda: current[0])
    _sync(provider, monkeypatch)
    responses.add(responses.GET, CODEX_RESETS_URL, status=429, headers={"Retry-After": retry_after})
    responses.add(responses.GET, CODEX_RESETS_URL, json=_fixture("codex_status.json"), status=200)
    provider.refresh(lambda snapshot: None)
    current[0] += blocked
    provider.refresh(lambda snapshot: None)
    assert len(responses.calls) == 1
    current[0] += advance
    provider.refresh(lambda snapshot: None)
    assert len(responses.calls) == 2

@responses.activate
def test_invalid_payload_does_not_commit_new_etag(monkeypatch):
    current = [NOW]
    provider = CodexResetsProvider(clock=lambda: current[0])
    _sync(provider, monkeypatch)
    responses.add(responses.GET, CODEX_RESETS_URL, json={"invalid": True}, status=200,
                  headers={"ETag": '"bad-payload"'})
    responses.add(responses.GET, CODEX_RESETS_URL, json=_fixture("codex_status.json"), status=200,
                  headers={"ETag": '"valid-payload"'})
    snapshots = []
    provider.refresh(snapshots.append)
    assert snapshots[0].status == SnapshotStatus.ERROR
    assert provider._etag is None
    current[0] += provider.MIN_INTERVAL
    provider.refresh(snapshots.append)
    assert "If-None-Match" not in responses.calls[1].request.headers
    assert provider._etag == '"valid-payload"'
