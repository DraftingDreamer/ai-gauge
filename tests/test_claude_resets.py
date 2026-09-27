import json
from datetime import datetime, timezone
from pathlib import Path

import responses

from aigauge.models import SnapshotStatus
from aigauge.providers.claude_resets import CLAUDE_RESETS_URL, ClaudeResetsProvider

FIXTURE = Path(__file__).parent / "fixtures" / "resets" / "claude_resets.json"
NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _sync(provider, monkeypatch):
    monkeypatch.setattr(provider, "_run_async", lambda work, on_done: on_done(work()))


def _fetch(monkeypatch, payload):
    provider = ClaudeResetsProvider(clock=lambda: NOW)
    monkeypatch.setattr(provider, "_get_json", lambda url, use_etag: payload)
    return provider._fetch_latest_event()


def test_ignores_newer_policy_and_selects_latest_reset(monkeypatch):
    event = _fetch(monkeypatch, _fixture())
    assert event.id == "2000000000000000003"
    assert event.kind == "banked"
    assert event.summary == "reset credit (Pro, Max + Team)"


def test_regular_reset_and_optional_scope(monkeypatch):
    payload = _fixture()
    events = payload["providers"]["claude"]["events"]
    without_scope = dict(events[1])
    without_scope.pop("scope")
    events[:] = [events[0], without_scope]
    event = _fetch(monkeypatch, payload)
    assert event.kind == "landed"
    assert event.summary == "limits refilled"
    assert event.id == "2000000000000000002"


def test_provisional_event_prefix_and_flag(monkeypatch):
    payload = _fixture()
    event_data = payload["providers"]["claude"]["events"][2]
    event_data["verification"] = "provisional"
    event_data.pop("scope")
    event = _fetch(monkeypatch, payload)
    assert event.provisional is True
    assert event.summary == "reset credit"
    assert event.detail.startswith("Unconfirmed (provisional). ")


def test_empty_events_return_none(monkeypatch):
    payload = _fixture()
    payload["providers"]["claude"]["events"] = []
    assert _fetch(monkeypatch, payload) is None


@responses.activate
def test_missing_provider_is_error_and_http_headers(monkeypatch):
    payload = _fixture()
    payload["providers"].pop("claude")
    responses.add(responses.GET, CLAUDE_RESETS_URL, json=payload, status=200)
    provider = ClaudeResetsProvider(clock=lambda: NOW)
    _sync(provider, monkeypatch)
    snapshots = []
    provider.refresh(snapshots.append)
    assert snapshots[0].status == SnapshotStatus.ERROR
    assert snapshots[0].error == "unexpected payload"
    headers = responses.calls[0].request.headers
    assert headers["User-Agent"] == (
        "ai-gauge/0.8.4 (+https://github.com/DraftingDreamer/ai-gauge)"
    )
    assert "If-None-Match" not in headers
