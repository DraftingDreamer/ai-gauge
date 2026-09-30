import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
import responses

from aigauge import __version__
from aigauge.models import SnapshotStatus
from aigauge.providers._resets_common import ResetEvent
from aigauge.providers.codex_resets import CODEX_RESETS_URL, CodexResetsProvider

FIXTURE = Path(__file__).parent / "fixtures" / "resets" / "codex_status.json"
NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _sync(provider, monkeypatch):
    monkeypatch.setattr(provider, "_run_async", lambda work, on_done: on_done(work()))


def _fetch(monkeypatch, payload):
    provider = CodexResetsProvider(clock=lambda: NOW)
    monkeypatch.setattr(provider, "_get_json", lambda url, use_etag: payload)
    return provider._fetch_latest_event()


@pytest.mark.parametrize(
    ("slot", "reset_type", "expected_kind", "expected_summary"),
    [
        ("scheduled_reset", "regular", "announced", "regular reset"),
        ("scheduled_reset", "banked", "announced", "banked reset"),
        ("latest_reset", "regular", "landed", "limits refilled"),
        ("latest_reset", "banked", "banked", "reset credit granted"),
    ],
)
def test_maps_each_event_type(monkeypatch, slot, reset_type, expected_kind, expected_summary):
    payload = {"data": {"scheduled_reset": None, "latest_reset": None}}
    template = _fixture()["data"][slot]
    payload["data"][slot] = {**template, "reset_type": reset_type}
    event = _fetch(monkeypatch, payload)
    assert event.kind == expected_kind
    assert event.summary == expected_summary
    assert event.id == template["id"]
    assert event.detail == template["text"]


def test_selects_latest_timestamp_and_scheduled_wins_tie(monkeypatch):
    payload = _fixture()
    scheduled = payload["data"]["scheduled_reset"]
    latest = payload["data"]["latest_reset"]
    latest["announced_at"] = "2026-09-27T00:00:00Z"
    assert _fetch(monkeypatch, payload).id == latest["id"]
    scheduled["announced_at"] = latest["announced_at"]
    event = _fetch(monkeypatch, payload)
    assert event.id == scheduled["id"]
    assert event.kind == "announced"


def test_empty_payload_and_observed_source(monkeypatch):
    payload = {"data": {"scheduled_reset": None, "latest_reset": None}}
    assert _fetch(monkeypatch, payload) is None
    observed = _fixture()
    observed["data"]["latest_reset"]["source"] = {
        "type": "observed", "url": "https://example.test/observed",
    }
    observed["data"]["scheduled_reset"] = None
    assert _fetch(monkeypatch, observed).url == "https://example.test/observed"


def test_same_id_key_changes_when_scheduled_becomes_latest(monkeypatch):
    scheduled = _fixture()["data"]["scheduled_reset"]
    scheduled["id"] = "same-id"
    latest = {"data": {"scheduled_reset": None, "latest_reset": {
        **scheduled, "reset_type": "regular",
    }}}
    announced = _fetch(monkeypatch, {"data": {
        "scheduled_reset": scheduled, "latest_reset": None,
    }})
    landed = _fetch(monkeypatch, latest)
    assert announced.key == "announced:same-id"
    assert landed.key == "landed:same-id"


@responses.activate
def test_etag_304_user_agent_and_cached_event(monkeypatch):
    provider = CodexResetsProvider(clock=lambda: NOW)
    _sync(provider, monkeypatch)
    responses.add(responses.GET, CODEX_RESETS_URL, json=_fixture(), status=200,
                  headers={"ETag": '"reset-v1"'})
    responses.add(responses.GET, CODEX_RESETS_URL, status=304)
    snapshots = []
    provider.refresh(snapshots.append)
    original = provider.latest_event
    provider._last_success_at = NOW - provider.MIN_INTERVAL
    provider.refresh(snapshots.append)
    assert responses.calls[0].request.headers["User-Agent"] == (
        f"ai-gauge/{__version__} (+https://github.com/DraftingDreamer/ai-gauge)"
    )
    assert responses.calls[1].request.headers["If-None-Match"] == '"reset-v1"'
    assert provider.latest_event == original
    assert snapshots[-1].raw["event_key"] == original.key


@responses.activate
def test_rate_limit_retains_event_and_blocks_until_retry_after(monkeypatch):
    current = [NOW]
    provider = CodexResetsProvider(clock=lambda: current[0])
    provider.latest_event = ResetEvent(
        "landed", "cached", NOW, "limits refilled", "cached detail", None
    )
    provider._last_success_at = NOW - provider.MIN_INTERVAL
    _sync(provider, monkeypatch)
    responses.add(responses.GET, CODEX_RESETS_URL, status=429,
                  headers={"Retry-After": "0"})
    responses.add(responses.GET, CODEX_RESETS_URL, json=_fixture(), status=200)
    snapshots = []
    provider.refresh(snapshots.append)
    assert snapshots[-1].status == SnapshotStatus.ERROR
    assert snapshots[-1].error == "rate limited"
    assert snapshots[-1].metrics[0].note == "cached detail"
    current[0] += timedelta(minutes=14, seconds=59)
    provider.refresh(snapshots.append)
    assert len(responses.calls) == 1
    current[0] += timedelta(seconds=1)
    provider.refresh(snapshots.append)
    assert len(responses.calls) == 2
    assert snapshots[-1].status == SnapshotStatus.OK


@pytest.mark.parametrize("failure", ["http", "network", "invalid_json"])
@responses.activate
def test_http_failures_keep_cached_event(monkeypatch, failure):
    provider = CodexResetsProvider(clock=lambda: NOW)
    provider.latest_event = ResetEvent(
        "banked", "cached", NOW, "reset credit granted", "cached", None
    )
    provider._last_success_at = NOW - provider.MIN_INTERVAL
    _sync(provider, monkeypatch)
    if failure == "http":
        responses.add(responses.GET, CODEX_RESETS_URL, status=503)
    elif failure == "network":
        responses.add(responses.GET, CODEX_RESETS_URL,
                      body=requests.ConnectionError("offline"))
    else:
        responses.add(responses.GET, CODEX_RESETS_URL, body="not json", status=200)
    snapshots = []
    provider.refresh(snapshots.append)
    assert snapshots[0].status == SnapshotStatus.ERROR
    assert snapshots[0].metrics[0].note == "cached"
    assert provider.latest_event.id == "cached"
    assert snapshots[0].error == {
        "http": "HTTP 503",
        "network": "network error: ConnectionError",
        "invalid_json": "invalid JSON",
    }[failure]


from types import SimpleNamespace
from unittest.mock import Mock
from aigauge.app import App
from aigauge.config import Config
from aigauge.providers.codex_resets import _parse_watch
from aigauge.providers._resets_common import ResetsFetchError

def watch_payload(source=None, **changes):
    payload = {
        "level": "elevated",
        "reset_chance_percent": 37,
        "forecast_window": "later this week",
        "observed_at": "2026-09-27T11:00:00Z",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
        "text": "Synthetic activity suggests a possible reset.",
        "source": source if source is not None else {"type": "observed"},
    }
    payload.update(changes)
    return payload

@pytest.mark.parametrize("source", [
    {"type": "observed"},
    {"type": "x_post", "author": "thsottiaux", "url": "https://example.test/post"},
])
def test_watch_parse_source_variants_and_invalid_watch_keeps_event(source):
    parsed = _parse_watch(watch_payload(source))
    assert parsed is not None
    assert parsed.source_url == source.get("url")
    provider = CodexResetsProvider(clock=lambda: NOW)
    provider._get_json = Mock(return_value={"data": {
        "latest_reset": {
            "id": "synthetic", "reset_type": "regular",
            "announced_at": "2026-09-27T12:00:00Z", "text": "Synthetic event",
            "source": {"type": "observed"},
        },
        "scheduled_reset": None,
        "active_watch": {"level": "strong"},
    }})
    assert provider._fetch_latest_event().id == "synthetic"
    assert provider.latest_watch is None

@pytest.mark.parametrize("changes", [
    {"reset_chance_percent": 101},
    {"reset_chance_percent": True},
    {"expires_at": "invalid"},
    {"observed_at": "2026-09-27T11:00:00"},
    {"source": {"type": "x_post", "url": "https://example.test/post"}},
])
def test_invalid_watch_fields_are_ignored(changes):
    assert _parse_watch(watch_payload(**changes)) is None

def test_watch_cache_on_304_and_error_and_no_notification(monkeypatch):
    provider = CodexResetsProvider(clock=lambda: NOW)
    payload = {"data": {
        "latest_reset": None, "scheduled_reset": None,
        "active_watch": watch_payload(),
    }}
    provider._get_json = Mock(side_effect=[payload, None, ResetsFetchError("HTTP 503")])
    monkeypatch.setattr(provider, "_run_async", lambda work, done: done(work()))
    snapshots = []
    for _ in range(3):
        provider._last_success_at = NOW - provider.MIN_INTERVAL
        provider.refresh(snapshots.append)
    assert [s.status for s in snapshots] == [
        SnapshotStatus.OK, SnapshotStatus.OK, SnapshotStatus.ERROR,
    ]
    assert all(s.raw["watch_key"] == snapshots[0].raw["watch_key"] for s in snapshots)
    app = App.__new__(App)
    app._providers = {"codex_resets": provider}
    app._config = Config()
    app._tray = SimpleNamespace(showMessage=Mock())
    app._on_reset_event("codex_resets")
    assert app._config.codex_resets.last_event_key is None
    app._tray.showMessage.assert_not_called()
