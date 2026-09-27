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
from aigauge.models import SnapshotStatus, UsageSnapshot
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
    app._config.codex_resets.last_event_key = "landed:old"
    provider.latest_event = event("announced", "same")
    app._on_reset_event("codex_resets")
    provider.latest_event = event("landed", "same")
    app._on_reset_event("codex_resets")
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
    app._config.codex_resets.last_event_key = "landed:old"
    opened = Mock()
    monkeypatch.setattr(app_module.QDesktopServices, "openUrl", opened)
    provider.latest_event = event(id="1")
    app._on_reset_event("codex_resets")
    provider.latest_event = event(id="2")
    app._on_reset_event("codex_resets")
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
