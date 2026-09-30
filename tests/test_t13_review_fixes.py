import html
import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree

import pytest
import responses

from aigauge import app as app_module
from aigauge.app import App, _snapshot_signature
from aigauge.config import Config
from aigauge.models import SnapshotStatus, UsageMetric, UsageSnapshot
from aigauge.providers import _resets_common, antigravity
from aigauge.providers._resets_common import ResetEvent, ResetWatch, ResetsProviderBase, build_snapshot
from aigauge.providers.antigravity import AntigravityProvider
from aigauge.providers.claude_resets import CLAUDE_RESETS_URL, ClaudeResetsProvider
from aigauge.providers.codex_resets import CODEX_RESETS_URL, CodexResetsProvider
from aigauge.windows_toast import build_toast_xml
from aigauge.widget import UsageWidget


NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
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


@pytest.mark.parametrize("provider_type,fixture,feed", [
    (CodexResetsProvider, "codex_status.json", "codex"),
    (ClaudeResetsProvider, "claude_resets.json", "claude"),
])
def test_feed_parsers_and_toast_drop_invalid_event_url(provider_type, fixture, feed, monkeypatch):
    payload = _fixture(fixture)
    bad = "ms-msdt:/id PCWDiagnostic"
    if feed == "codex":
        payload["data"]["scheduled_reset"] = None
        payload["data"]["latest_reset"]["source"]["url"] = bad
        provider = provider_type()
        provider._get_json = lambda url, use_etag: payload
        event = provider._fetch_latest_event()
    else:
        reset = payload["providers"]["claude"]["events"][2]
        reset["url"] = bad
        provider = provider_type()
        provider._get_json = lambda url, use_etag: payload
        event = provider._fetch_latest_event()
    assert event.url is None
    root = ElementTree.fromstring(build_toast_xml("title", "message", event.url))
    assert "launch" not in root.attrib
    app = App.__new__(App)
    app._last_reset_notification_url = event.url
    opened = Mock()
    monkeypatch.setattr(app_module.QDesktopServices, "openUrl", opened)
    app._on_reset_notification_clicked()
    opened.assert_not_called()


class _FailingProvider(ResetsProviderBase):
    name = "t13_failing_resets"
    display_name = "Test Resets"

    def _fetch_latest_event(self):
        raise RuntimeError("format failure")


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


def _watch(level="elevated", observed=NOW):
    return ResetWatch(level, 40, "1-2 days", observed, NOW + timedelta(days=1), "watch text", None)


def test_reset_signatures_ignore_relative_age_but_track_event_dismissal_and_watch():
    event = ResetEvent("landed", "1", NOW, "summary", "detail", None)
    five = build_snapshot("codex_resets", event, None, NOW + timedelta(minutes=5))
    ten = build_snapshot("codex_resets", event, None, NOW + timedelta(minutes=10))
    assert _snapshot_signature(five) == _snapshot_signature(ten)
    newer = ResetEvent("landed", "2", NOW, "summary", "detail", None)
    assert _snapshot_signature(five) != _snapshot_signature(
        build_snapshot("codex_resets", newer, None, NOW + timedelta(minutes=10))
    )
    assert _snapshot_signature(five) != _snapshot_signature(
        build_snapshot("codex_resets", event, event.key, NOW + timedelta(minutes=10))
    )
    watch_snapshot = build_snapshot("codex_resets", event, None, NOW, watch=_watch())
    changed_watch = build_snapshot("codex_resets", event, None, NOW, watch=_watch("strong"))
    assert _snapshot_signature(watch_snapshot) != _snapshot_signature(changed_watch)


def test_stale_error_retry_skips_only_reset_providers():
    app = App.__new__(App)
    metric = UsageMetric("stale", None, None, None, None, None, None)
    app._snapshots = {
        "codex_resets": UsageSnapshot("codex_resets", SnapshotStatus.ERROR, metrics=[metric]),
        "claude_resets": UsageSnapshot("claude_resets", SnapshotStatus.ERROR, metrics=[metric]),
    }
    assert app._stale_error_retry_time(NOW.replace(tzinfo=None)) is None
    app._snapshots["claude"] = UsageSnapshot("claude", SnapshotStatus.ERROR, metrics=[metric])
    assert app._stale_error_retry_time(NOW.replace(tzinfo=None)) == NOW.replace(tzinfo=None) + timedelta(minutes=1)


def _provider_app(config):
    app = App.__new__(App)
    app._config = config
    app._providers = {}
    app._snapshots = {}
    app._widget = SimpleNamespace(
        _tiles={}, ensure_tile=lambda name, label: app._widget._tiles.setdefault(name, label),
        remove_tile=lambda name: app._widget._tiles.pop(name, None),
    )
    app._sync_usage_cache = lambda: None
    return app


def test_antigravity_latch_survives_provider_rebuild_disable_and_reenable(monkeypatch):
    config = Config()
    config.providers.claude = config.providers.codex = False
    config.providers.copilot = config.providers.openrouter = False
    config.providers.antigravity = True
    app = _provider_app(config)
    calls = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps({
        "status": "SUCCESS", "num_turns": 1,
        "usage": {"total_tokens": 1},
    }), ""))
    monkeypatch.setattr(antigravity, "_invoke_cli", calls)
    monkeypatch.setattr(antigravity, "resolve_cli", lambda _: "agy")
    monkeypatch.setattr(AntigravityProvider, "_run_async", lambda self, work, done: done(work()))
    app._build_providers()
    app._providers["antigravity"].refresh(lambda snapshot: None)
    assert antigravity._PROCESS_LATCHED_ERROR
    app._build_providers()
    app._providers["antigravity"].refresh(lambda snapshot: None)
    assert calls.call_count == 1
    config.providers.antigravity = False
    app._build_providers()
    config.providers.antigravity = True
    app._build_providers()
    snapshots = []
    app._providers["antigravity"].refresh(snapshots.append)
    assert calls.call_count == 1
    assert snapshots[0].error == antigravity._PROCESS_LATCHED_ERROR


def test_reset_fetch_state_survives_provider_rebuild(monkeypatch):
    config = Config()
    config.providers.claude = config.providers.codex = False
    config.providers.copilot = config.providers.openrouter = False
    config.providers.codex_resets = True
    app = _provider_app(config)
    fetch = Mock()

    def fetch_event(provider):
        fetch(provider)
        provider.latest_watch = _watch()
        provider._pending_etag = '"reset-state"'
        fetch.return_value = ResetEvent("landed", "new", NOW, "summary", "detail", None)
        return fetch.return_value

    monkeypatch.setattr(CodexResetsProvider, "_fetch_latest_event", fetch_event)
    monkeypatch.setattr(ResetsProviderBase, "_run_async", lambda self, work, done: done(work()))
    monkeypatch.setattr(app_module, "datetime", SimpleNamespace(now=lambda: NOW.replace(tzinfo=None)))
    app._build_providers()
    app._providers["codex_resets"].refresh(lambda snapshot: None)
    app._build_providers()
    rebuilt = app._providers["codex_resets"]
    assert rebuilt.latest_event.id == "new"
    assert rebuilt.latest_watch.key == _watch().key
    assert rebuilt._etag == '"reset-state"'
    app._providers["codex_resets"].refresh(lambda snapshot: None)
    fetch.assert_called_once()


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


def test_save_failure_does_not_break_snapshot_or_notification(monkeypatch, caplog):
    config = Config()
    config.codex_resets.last_event_key = "landed:old"
    config.codex_resets.notify_landed = True
    monkeypatch.setattr(Config, "save", Mock(side_effect=OSError("disk full")))
    event = ResetEvent("landed", "new", NOW, "summary", "detail", "ms-msdt:/id PCWDiagnostic")
    provider = SimpleNamespace(latest_event=event, name="codex_resets")
    app = App.__new__(App)
    app._config = config
    app._providers = {"codex_resets": provider}
    app._snapshots = {}
    app._cleared_sessions = set()
    app._cycle_signatures = {}
    app._inflight = {"codex_resets"}
    app._refresh_queue = ["next"]
    app._history = SimpleNamespace(record_snapshot=lambda snapshot: [])
    app._ratio = SimpleNamespace(record_snapshot=Mock(), display_estimate=Mock(return_value=None), current_estimate=Mock(return_value=None))
    app._widget = SimpleNamespace(update_snapshot=Mock(), set_ratio=Mock())
    app._local_usage_on_snapshot = Mock()
    app._ratio_recent = Mock(return_value=[])
    app._start_next_refresh = Mock()
    app._enqueue_reset_notification = Mock()
    monkeypatch.setattr(app_module.QTimer, "singleShot", Mock())
    snapshot = build_snapshot("codex_resets", event, None, NOW)
    with caplog.at_level(logging.ERROR):
        app._on_snapshot(snapshot)
    assert "codex_resets" not in app._inflight
    app._enqueue_reset_notification.assert_called_once_with(
        "Codex reset landed",
        "Usage limits were refilled. Click to open the post.",
        None, "codex_resets", "landed", "new",
    )
    assert "failed to save reset event" in caplog.text


def test_dismiss_save_failure_is_logged_and_still_hides_event(monkeypatch, caplog):
    config = Config()
    monkeypatch.setattr(Config, "save", Mock(side_effect=OSError("disk full")))
    provider = SimpleNamespace(
        name="codex_resets", latest_event=ResetEvent("landed", "1", NOW, "summary", "detail", None),
        latest_watch=None, dismissed_event_key=None, dismissed_watch_key=None,
    )
    app = App.__new__(App)
    app._config = config
    app._providers = {"codex_resets": provider}
    app._snapshots = {}
    app._widget = SimpleNamespace(update_snapshot=Mock())
    with caplog.at_level(logging.ERROR):
        app._on_dismiss_requested("codex_resets")
    assert app._snapshots["codex_resets"].metrics == []
    assert "failed to save reset dismissal" in caplog.text


def test_reset_tile_uses_plain_text_and_escaped_tooltip(qtbot):
    widget = UsageWidget(Config())
    qtbot.addWidget(widget)
    tile = widget.ensure_tile("codex_resets", "Codex Resets")
    event = ResetEvent("landed", "1", NOW, "<b>x</b>", '<a href="https://e.test">y</a>', None)
    tile.set_snapshot(build_snapshot("codex_resets", event, None, NOW))
    row = tile._rows[0]
    assert row.label.textFormat().name == "PlainText"
    assert row.reset.textFormat().name == "PlainText"
    assert row.reset.text() == "<b>x</b>, just now"
    assert "&lt;a href=&quot;https://e.test&quot;&gt;y&lt;/a&gt;" in row.toolTip()
    assert html.escape(event.detail, quote=True) in row.toolTip()
