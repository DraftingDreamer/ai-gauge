from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtWidgets import QSystemTrayIcon

from aigauge import app as app_module
from aigauge import config as config_module
from aigauge import widget as widget_module
from aigauge.app import App, _enabled_providers
from aigauge.config import Config, ResetsConfig, display_name_for_account
from aigauge.menubar import status_items
from aigauge.models import SnapshotStatus, UsageMetric, UsageSnapshot
from aigauge.providers._resets_common import ResetEvent, build_snapshot
from aigauge.settings_dialog import SettingsDialog
from aigauge.widget import UsageWidget


NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


def event(kind="landed", id="1", summary="regular reset"):
    return ResetEvent(
        kind=kind, id=id, at=NOW, summary=summary, detail="Synthetic post",
        url=f"https://example.test/{id}/{kind}",
    )


def make_app(monkeypatch, name="codex_resets", tray=None):
    config = Config()
    config.providers.codex_resets = name == "codex_resets"
    config.providers.claude_resets = name == "claude_resets"
    saves = Mock()
    monkeypatch.setattr(Config, "save", saves)
    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True)
    )
    provider = SimpleNamespace(
        name=name, latest_event=None, dismissed_event_key=None,
        _fetch_latest_event=Mock(),
    )
    app = App.__new__(App)
    app._config = config
    app._providers = {name: provider}
    app._snapshots = {}
    app._widget = SimpleNamespace(update_snapshot=Mock())
    app._tray = tray
    app._last_reset_notification_url = None
    return app, provider, saves


def test_config_defaults_and_legacy_json(tmp_path, monkeypatch):
    config = Config()
    assert not config.providers.codex_resets
    assert not config.providers.claude_resets
    assert config.codex_resets == ResetsConfig()
    assert config.claude_resets == ResetsConfig()
    assert config.codex_resets.notify_announced
    assert config.codex_resets.notify_landed
    assert config.codex_resets.notify_banked
    assert config.codex_resets.last_event_key is None
    assert config.codex_resets.dismissed_event_key is None
    assert display_name_for_account(config, "codex_resets") == "Codex Resets"
    assert display_name_for_account(config, "claude_resets") == "Claude Resets"
    path = tmp_path / "config.json"
    path.write_text('{"providers": {"claude": false}}', encoding="utf-8")
    monkeypatch.setattr(config_module, "config_path", lambda: path)
    loaded = Config.load()
    assert loaded.providers.codex_resets is False
    assert loaded.providers.claude_resets is False
    assert loaded.codex_resets == ResetsConfig()
    assert loaded.claude_resets == ResetsConfig()


def test_build_providers_restores_dismissal_and_ensures_tiles(monkeypatch):
    app, _, _ = make_app(monkeypatch)
    app._config.providers.claude_resets = True
    app._config.codex_resets.dismissed_event_key = "landed:old"
    app._config.claude_resets.dismissed_event_key = "banked:old"
    app._config.providers.claude = False
    app._config.providers.codex = False
    app._config.providers.copilot = False
    tiles = []
    app._widget = SimpleNamespace(
        _tiles={}, ensure_tile=lambda name, title: tiles.append((name, title)),
        remove_tile=Mock(),
    )
    monkeypatch.setattr(app, "_sync_usage_cache", lambda: None)
    assert _enabled_providers(app._config)[-2:] == (
        "codex_resets", "claude_resets"
    )
    app._build_providers()
    assert app._providers["codex_resets"].dismissed_event_key == "landed:old"
    assert app._providers["claude_resets"].dismissed_event_key == "banked:old"
    assert tiles == [
        ("codex_resets", "Codex Resets"),
        ("claude_resets", "Claude Resets"),
    ]


@pytest.mark.parametrize("name", ["codex_resets", "claude_resets"])
def test_first_event_is_recorded_without_notification(monkeypatch, name):
    tray = Mock()
    app, provider, saves = make_app(monkeypatch, name, tray)
    provider.latest_event = event()
    app._on_reset_event(name)
    assert getattr(app._config, name).last_event_key == "landed:1"
    saves.assert_called_once_with()
    tray.showMessage.assert_not_called()
    app._on_reset_event(name)
    saves.assert_called_once_with()
    tray.showMessage.assert_not_called()


@pytest.mark.parametrize(
    "name,kind,title,message",
    [
        ("codex_resets", "announced", "Codex reset announced",
         "A regular reset was announced. Click to open the post."),
        ("codex_resets", "landed", "Codex reset landed",
         "Usage limits were refilled. Click to open the post."),
        ("codex_resets", "banked", "Codex reset credit granted",
         "A banked reset is available to redeem in Codex. Click to open the post."),
        ("claude_resets", "landed", "Claude reset landed",
         "Usage limits were refilled. Click to open the post."),
        ("claude_resets", "banked", "Claude reset credit granted",
         "A banked reset is available to redeem in Claude. Click to open the post."),
    ],
)
def test_new_event_notifies_by_kind_and_respects_toggle(
    monkeypatch, name, kind, title, message,
):
    tray = Mock()
    app, provider, saves = make_app(monkeypatch, name, tray)
    settings = getattr(app._config, name)
    settings.last_event_key = "landed:old"
    provider.latest_event = event(kind)
    app._on_reset_event(name)
    tray.showMessage.assert_called_once_with(
        title, message, QSystemTrayIcon.MessageIcon.Information
    )
    assert app._last_reset_notification_url == provider.latest_event.url
    assert settings.last_event_key == provider.latest_event.key
    app._on_reset_event(name)
    tray.showMessage.assert_called_once()
    saves.assert_called_once()
    setattr(settings, f"notify_{kind}", False)
    provider.latest_event = event(kind, id="2")
    app._on_reset_event(name)
    tray.showMessage.assert_called_once()
    assert settings.last_event_key == provider.latest_event.key
    assert saves.call_count == 2


def test_same_id_announced_then_landed_notifies_twice(monkeypatch):
    tray = Mock()
    app, provider, _ = make_app(monkeypatch, tray=tray)
    timers = []
    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        app_module.QTimer, "singleShot", lambda delay, callback: timers.append(
            (delay, callback)
        )
    )
    app._config.codex_resets.last_event_key = "landed:old"
    provider.latest_event = event("announced", "same")
    app._on_reset_event("codex_resets")
    provider.latest_event = event("landed", "same")
    app._on_reset_event("codex_resets")
    assert tray.showMessage.call_count == 1
    clock[0] += app_module._RESET_NOTIFICATION_SPACING_MS / 1000
    timers.pop()[1]()
    assert tray.showMessage.call_count == 2
    assert app._config.codex_resets.last_event_key == "landed:same"


def test_no_tray_or_unavailable_tray_still_records_event(monkeypatch):
    app, provider, saves = make_app(monkeypatch)
    app._config.codex_resets.last_event_key = "landed:old"
    provider.latest_event = event()
    app._on_reset_event("codex_resets")
    assert app._config.codex_resets.last_event_key == "landed:1"
    saves.assert_called_once()
    tray = Mock()
    app._tray = tray
    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False)
    )
    provider.latest_event = event(id="2")
    app._on_reset_event("codex_resets")
    tray.showMessage.assert_not_called()


def test_snapshot_path_records_reset_event(monkeypatch):
    tray = Mock()
    app, provider, saves = make_app(monkeypatch, tray=tray)
    provider.latest_event = event()
    app._cleared_sessions = set()
    app._cycle_signatures = {}
    app._inflight = {"codex_resets"}
    app._refresh_queue = ["next-provider"]
    app._history = SimpleNamespace(record_snapshot=lambda snapshot: [])
    app._ratio = SimpleNamespace(
        record_snapshot=Mock(), display_estimate=Mock(return_value=None),
        current_estimate=Mock(return_value=None),
    )
    app._widget.set_ratio = Mock()
    app._local_usage_on_snapshot = Mock()
    app._ratio_recent = Mock(return_value=[])
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *args: None)
    snapshot = build_snapshot("codex_resets", provider.latest_event, None, NOW)
    app._on_snapshot(snapshot)
    assert app._config.codex_resets.last_event_key == "landed:1"
    saves.assert_called_once()
    app._widget.update_snapshot.assert_called_once_with(
        snapshot, "Codex Resets"
    )


def test_mcp_cache_excludes_reset_snapshots(monkeypatch):
    app, provider, _ = make_app(monkeypatch)
    app._config.mcp_enabled = True
    reset_snapshot = build_snapshot("codex_resets", event(), None, NOW)
    usage_snapshot = UsageSnapshot(provider="copilot", status=SnapshotStatus.OK)
    app._snapshots = {
        "codex_resets": reset_snapshot, "copilot": usage_snapshot,
    }
    write = Mock()
    monkeypatch.setattr(app_module, "write_usage_cache", write)
    app._sync_usage_cache()
    write.assert_called_once_with({"copilot": usage_snapshot})


def test_notification_click_opens_last_post(monkeypatch):
    tray = Mock()
    app, provider, _ = make_app(monkeypatch, tray=tray)
    timers = []
    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        app_module.QTimer, "singleShot", lambda delay, callback: timers.append(
            (delay, callback)
        )
    )
    app._config.codex_resets.last_event_key = "landed:old"
    opened = Mock()
    monkeypatch.setattr(app_module.QDesktopServices, "openUrl", opened)
    provider.latest_event = event(id="1")
    app._on_reset_event("codex_resets")
    provider.latest_event = event(id="2")
    app._on_reset_event("codex_resets")
    clock[0] += app_module._RESET_NOTIFICATION_SPACING_MS / 1000
    timers.pop()[1]()
    app._on_reset_notification_clicked()
    assert opened.call_count == 1
    assert opened.call_args.args[0].toString() == event(id="2").url


def test_dismiss_uses_cached_event_and_new_event_reappears(monkeypatch):
    app, provider, saves = make_app(monkeypatch)
    provider.latest_event = event()
    app._on_dismiss_requested("codex_resets")
    assert app._config.codex_resets.dismissed_event_key == "landed:1"
    assert provider.dismissed_event_key == "landed:1"
    saves.assert_called_once()
    snapshot = app._snapshots["codex_resets"]
    assert snapshot.metrics == []
    app._widget.update_snapshot.assert_called_once_with(
        snapshot, "Codex Resets"
    )
    provider._fetch_latest_event.assert_not_called()
    provider.latest_event = event(id="2")
    refreshed = build_snapshot(
        provider.name, provider.latest_event, provider.dismissed_event_key,
        NOW + timedelta(minutes=1),
    )
    assert len(refreshed.metrics) == 1


@pytest.mark.parametrize("name", ["codex_resets", "claude_resets"])
def test_widget_event_controls_status_and_links(qtbot, monkeypatch, name):
    widget = UsageWidget(Config())
    qtbot.addWidget(widget)
    widget.show()
    post = event()
    tile = widget.ensure_tile(name, display_name_for_account(Config(), name))
    opened = Mock()
    monkeypatch.setattr(widget_module.QDesktopServices, "openUrl", opened)
    tile.set_snapshot(build_snapshot(name, post, None, NOW))
    assert not tile.dismiss_btn.isHidden()
    assert not tile.open_btn.isHidden()
    assert f"via {'Codex' if name == 'codex_resets' else 'Claude'} Resets" in tile.status.text()
    with qtbot.waitSignal(widget.dismiss_requested) as signal:
        tile.dismiss_btn.click()
    assert signal.args == [name]
    tile.open_btn.click()
    assert opened.call_args.args[0].toString() == post.url
    tracker_url = f"https://{'codex' if name == 'codex_resets' else 'claude'}-resets.com"
    tile.status.linkActivated.emit(tracker_url)
    assert opened.call_args.args[0].toString() == tracker_url
    with qtbot.waitSignal(widget.details_requested) as details:
        tile.status.linkActivated.emit("details")
    assert details.args == [name]
    tile.set_snapshot(build_snapshot(name, post, post.key, NOW))
    assert tile.dismiss_btn.isHidden()
    assert tile.open_btn.isHidden()
    assert "no new announcements" in tile.status.text()
    tile.set_snapshot(build_snapshot(name, None, None, NOW))
    assert tile.dismiss_btn.isHidden()
    assert "no new announcements" in tile.status.text()


def test_other_provider_error_link_still_requests_details(qtbot):
    widget = UsageWidget(Config())
    qtbot.addWidget(widget)
    tile = widget.ensure_tile("copilot", "Copilot")
    tile.set_snapshot(UsageSnapshot(
        provider="copilot", status=SnapshotStatus.ERROR, error="failed",
    ))
    with qtbot.waitSignal(widget.details_requested) as signal:
        tile.status.linkActivated.emit("details")
    assert signal.args == ["copilot"]


def test_settings_reset_alerts_tab_and_save(qtbot, monkeypatch):
    monkeypatch.setattr("aigauge.settings_dialog.resolve_cli", lambda _: None)
    monkeypatch.setattr(
        "aigauge.settings_dialog.set_start_at_login", lambda _: None
    )
    monkeypatch.setattr(Config, "save", lambda self: None)
    config = Config()
    dialog = SettingsDialog(config)
    qtbot.addWidget(dialog)
    index = next(
        i for i in range(dialog.tabs.count())
        if dialog.tabs.tabText(i) == "Reset alerts"
    )
    assert not dialog.codex_resets_cb.isChecked()
    assert not dialog.claude_resets_cb.isChecked()
    dialog.codex_resets_cb.setChecked(True)
    dialog.claude_resets_cb.setChecked(True)
    dialog.codex_notify_announced_cb.setChecked(False)
    dialog.codex_notify_landed_cb.setChecked(False)
    dialog.codex_notify_banked_cb.setChecked(False)
    dialog.claude_notify_landed_cb.setChecked(False)
    dialog.claude_notify_banked_cb.setChecked(False)
    dialog.apply_to(config)
    assert config.providers.codex_resets
    assert config.providers.claude_resets
    assert not config.codex_resets.notify_announced
    assert not config.codex_resets.notify_landed
    assert not config.codex_resets.notify_banked
    assert not config.claude_resets.notify_landed
    assert not config.claude_resets.notify_banked
    for name in ("codex_resets", "claude_resets"):
        dialog.show_provider(name)
        assert dialog.tabs.currentIndex() == index


def test_menubar_excludes_reset_providers():
    config = Config()
    providers = ("claude", "codex_resets", "claude_resets")
    assert len(status_items({}, providers, config)) == 1


import html
import json
import logging
import subprocess
from pathlib import Path
from xml.etree import ElementTree
from aigauge.app import _snapshot_signature
from aigauge.providers import _resets_common, antigravity
from aigauge.providers._resets_common import ResetWatch, ResetsProviderBase
from aigauge.providers.antigravity import AntigravityProvider
from aigauge.providers.claude_resets import ClaudeResetsProvider
from aigauge.providers.codex_resets import CodexResetsProvider, _parse_watch
from aigauge.windows_toast import build_toast_xml

def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

def _watch(level="elevated", observed=NOW):
    return ResetWatch(level, 40, "1-2 days", observed, NOW + timedelta(days=1), "watch text", None)

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
        "Usage limits were refilled.",
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

def test_dismiss_event_and_watch_without_fetch(qtbot, monkeypatch):
    config = Config()
    save = Mock()
    monkeypatch.setattr(Config, "save", save)
    widget = UsageWidget(config)
    qtbot.addWidget(widget)
    watch = _parse_watch(watch_payload())
    provider = SimpleNamespace(
        name="codex_resets", latest_event=event(), latest_watch=watch,
        dismissed_event_key=None, dismissed_watch_key=None,
        _fetch_latest_event=Mock(),
    )
    app = App.__new__(App)
    app._config = config
    app._providers = {"codex_resets": provider}
    app._snapshots = {}
    app._widget = widget
    widget.update_snapshot(build_snapshot("codex_resets", event(), None, NOW, watch=watch), "Codex Resets")
    app._on_dismiss_requested("codex_resets")
    assert config.codex_resets.dismissed_event_key == event().key
    assert config.codex_resets.dismissed_watch_key == watch.key
    assert widget._tiles["codex_resets"].isHidden()
    provider._fetch_latest_event.assert_not_called()
    save.assert_called_once()
    same = _parse_watch(watch_payload(
        reset_chance_percent=55, forecast_window="slightly different text"
    ))
    snapshot = build_snapshot("codex_resets", event(), event().key, NOW,
                              watch=same, dismissed_watch_key=watch.key)
    assert snapshot.raw["dismissed"]
    promoted = _parse_watch(watch_payload(level="strong"))
    snapshot = build_snapshot("codex_resets", event(), event().key, NOW,
                              watch=promoted, dismissed_watch_key=watch.key)
    assert not snapshot.raw["dismissed"]
    widget.update_snapshot(snapshot, "Codex Resets")
    assert not widget._tiles["codex_resets"].isHidden()
    changed = _parse_watch(watch_payload(observed_at="2026-09-27T11:05:00Z"))
    assert not build_snapshot("codex_resets", event(), event().key, NOW,
                              watch=changed, dismissed_watch_key=watch.key).raw["dismissed"]
    assert build_snapshot("codex_resets", event(), event().key, NOW,
                          watch=watch, dismissed_watch_key=promoted.key).raw["dismissed"]

def test_expired_watch_is_not_saved_on_event_dismiss(monkeypatch):
    config = Config()
    monkeypatch.setattr(Config, "save", Mock())
    expired = _parse_watch(watch_payload(expires_at="2026-09-26T11:00:00Z"))
    provider = SimpleNamespace(
        name="codex_resets", latest_event=event(), latest_watch=expired,
        dismissed_event_key=None, dismissed_watch_key=None,
    )
    app = App.__new__(App)
    app._config = config
    app._providers = {"codex_resets": provider}
    app._snapshots = {}
    app._widget = SimpleNamespace(update_snapshot=Mock())
    app._on_dismiss_requested("codex_resets")
    assert config.codex_resets.dismissed_event_key == event().key
    assert config.codex_resets.dismissed_watch_key is None

def test_legacy_config_without_watch_key_loads(tmp_path, monkeypatch):
    from aigauge import config as config_module

    path = tmp_path / "config.json"
    path.write_text('{"codex_resets":{"dismissed_event_key":"landed:old"}}', encoding="utf-8")
    monkeypatch.setattr(config_module, "config_path", lambda: path)
    config = Config.load()
    assert config.codex_resets.dismissed_watch_key is None

FIXTURES = Path(__file__).parent / "fixtures" / "resets"

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


def test_reset_signature_tracks_display_content_and_watch_expiry():
    original = ResetEvent("landed", "same", NOW, "old summary", "detail", None)
    base = build_snapshot("codex_resets", original, None, NOW)
    corrected = ResetEvent("landed", "same", NOW, "new summary", "detail", None)
    assert _snapshot_signature(base) != _snapshot_signature(
        build_snapshot("codex_resets", corrected, None, NOW)
    )

    watch_40 = _watch()
    watch_90 = ResetWatch(
        watch_40.level, 90, watch_40.forecast_window, watch_40.observed_at,
        watch_40.expires_at, watch_40.text, watch_40.source_url,
    )
    with_watch = build_snapshot("codex_resets", None, None, NOW, watch=watch_40)
    changed_chance = build_snapshot("codex_resets", None, None, NOW, watch=watch_90)
    expired_watch = build_snapshot(
        "codex_resets", None, None, watch_40.expires_at, watch=watch_40
    )
    assert _snapshot_signature(with_watch) != _snapshot_signature(changed_chance)
    assert _snapshot_signature(with_watch) != _snapshot_signature(expired_watch)


@pytest.mark.parametrize("case", ["expired_watch", "dismissed_event", "claude"])
def test_on_snapshot_does_not_restore_reset_metrics_after_error(case, monkeypatch):
    app = App.__new__(App)
    app._config = Config()
    app._config.mcp_enabled = False
    app._cleared_sessions = set()
    app._snapshots = {}
    app._cycle_signatures = {}
    app._inflight = set()
    app._refresh_queue = []
    app._current_refresh_manual = True
    app._history = SimpleNamespace(record_snapshot=lambda snapshot: [])
    app._ratio = SimpleNamespace(
        record_snapshot=Mock(), display_estimate=Mock(return_value=None),
        current_estimate=Mock(return_value=None),
    )
    app._widget = SimpleNamespace(
        update_snapshot=Mock(), set_ratio=Mock(), set_refreshing=Mock(),
    )
    app._ratio_recent = Mock(return_value=[])
    app._local_usage_on_snapshot = Mock()
    app._cycle_changed = Mock(return_value=False)
    app._update_tray = Mock()
    app._schedule_next_refresh = Mock()
    monkeypatch.setattr(app_module.QTimer, "singleShot", Mock())

    if case == "expired_watch":
        watch = _watch()
        previous = build_snapshot("codex_resets", None, None, NOW, watch=watch)
        failed = build_snapshot(
            "codex_resets", None, None, watch.expires_at, error="HTTP 503",
            watch=watch,
        )
        expected_metrics = []
    elif case == "dismissed_event":
        post = event()
        previous = build_snapshot("codex_resets", post, None, NOW)
        failed = build_snapshot(
            "codex_resets", post, post.key, NOW, error="HTTP 503"
        )
        expected_metrics = []
    else:
        stale = UsageMetric("stale Claude metric", None, None, None, None, None, None)
        previous = UsageSnapshot("claude", SnapshotStatus.OK, metrics=[stale])
        failed = UsageSnapshot("claude", SnapshotStatus.ERROR, metrics=[])
        expected_metrics = [stale]

    app._snapshots[previous.provider] = previous
    app._on_snapshot(failed)
    assert app._snapshots[failed.provider].metrics == expected_metrics


def test_reset_signature_tracks_event_absolute_time():
    original = ResetEvent("landed", "same", NOW, "summary", "detail", None)
    corrected = ResetEvent(
        "landed", "same", NOW + timedelta(minutes=1), "summary", "detail", None
    )
    original_snapshot = build_snapshot("codex_resets", original, None, NOW)
    corrected_snapshot = build_snapshot("codex_resets", corrected, None, NOW)

    assert _snapshot_signature(original_snapshot) != _snapshot_signature(
        corrected_snapshot
    )


def test_reset_signature_tracks_event_url_value():
    common = ("landed", "same", NOW, "summary", "detail")
    original = ResetEvent(*common, "https://x.example/a")
    corrected = ResetEvent(*common, "https://x.example/b")
    original_snapshot = build_snapshot("codex_resets", original, None, NOW)
    corrected_snapshot = build_snapshot("codex_resets", corrected, None, NOW)

    assert _snapshot_signature(original_snapshot) != _snapshot_signature(
        corrected_snapshot
    )


def test_reset_signature_tracks_watch_url_value():
    base = _watch()
    original = ResetWatch(
        base.level, base.reset_chance_percent, base.forecast_window,
        base.observed_at, base.expires_at, base.text, "https://x.example/a",
    )
    corrected = ResetWatch(
        base.level, base.reset_chance_percent, base.forecast_window,
        base.observed_at, base.expires_at, base.text, "https://x.example/b",
    )
    original_snapshot = build_snapshot("codex_resets", None, None, NOW, watch=original)
    corrected_snapshot = build_snapshot("codex_resets", None, None, NOW, watch=corrected)

    assert _snapshot_signature(original_snapshot) != _snapshot_signature(
        corrected_snapshot
    )
