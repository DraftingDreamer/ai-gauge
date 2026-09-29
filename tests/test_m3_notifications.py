from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtWidgets import QSystemTrayIcon

from aigauge import app as app_module
from aigauge.app import App
from aigauge.config import Config
from aigauge.providers._resets_common import ResetEvent


NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


def event(kind, event_id, provider):
    return ResetEvent(
        kind=kind,
        id=event_id,
        at=NOW,
        summary="regular reset",
        detail="Private post content",
        url=f"https://example.test/{provider}/{event_id}/{kind}",
    )


def make_app(monkeypatch, *, tray=None):
    config = Config()
    config.codex_resets.last_event_key = "landed:old-codex"
    config.claude_resets.last_event_key = "landed:old-claude"
    saves = Mock()
    monkeypatch.setattr(Config, "save", saves)
    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True)
    )
    providers = {
        "codex_resets": SimpleNamespace(
            latest_event=None, name="codex_resets"
        ),
        "claude_resets": SimpleNamespace(
            latest_event=None, name="claude_resets"
        ),
    }
    app = App.__new__(App)
    app._config = config
    app._providers = providers
    app._tray = tray
    return app, providers, saves


def test_two_providers_are_queued_and_last_shown_url_is_opened(monkeypatch):
    tray = Mock()
    app, providers, _ = make_app(monkeypatch, tray=tray)
    timers = []
    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        app_module.QTimer, "singleShot", lambda delay, callback: timers.append(
            (delay, callback)
        )
    )
    opened = Mock()
    monkeypatch.setattr(app_module.QDesktopServices, "openUrl", opened)

    providers["codex_resets"].latest_event = event(
        "landed", "codex-new", "codex"
    )
    providers["claude_resets"].latest_event = event(
        "landed", "claude-new", "claude"
    )
    app._on_reset_event("codex_resets")
    app._on_reset_event("claude_resets")

    tray.showMessage.assert_called_once()
    assert app._last_reset_notification_url == (
        "https://example.test/codex/codex-new/landed"
    )
    assert len(timers) == 1
    assert timers[0][0] == app_module._RESET_NOTIFICATION_SPACING_MS
    clock[0] += app_module._RESET_NOTIFICATION_SPACING_MS / 1000
    timers.pop()[1]()
    assert tray.showMessage.call_count == 2
    assert app._last_reset_notification_url == (
        "https://example.test/claude/claude-new/landed"
    )
    app._on_reset_notification_clicked()
    assert opened.call_args.args[0].toString() == app._last_reset_notification_url


def test_notification_logging_records_shown_without_post_content(
    monkeypatch, caplog
):
    caplog.set_level("INFO", logger="aigauge.app")
    app, providers, _ = make_app(monkeypatch, tray=Mock())
    providers["codex_resets"].latest_event = event("landed", "new", "codex")
    app._on_reset_event("codex_resets")
    assert "reset notification shown provider=codex_resets kind=landed event_id=new" in caplog.text
    assert "Private post content" not in caplog.text


def test_notification_logging_records_missing_tray(monkeypatch, caplog):
    caplog.set_level("INFO", logger="aigauge.app")
    app, providers, _ = make_app(monkeypatch)
    providers["codex_resets"].latest_event = event("landed", "new", "codex")
    app._on_reset_event("codex_resets")
    assert "provider=codex_resets kind=landed reason=no tray" in caplog.text


def test_notification_logging_records_disabled_setting(monkeypatch, caplog):
    caplog.set_level("INFO", logger="aigauge.app")
    app, providers, _ = make_app(monkeypatch, tray=Mock())
    app._config.codex_resets.notify_landed = False
    providers["codex_resets"].latest_event = event("landed", "new", "codex")
    app._on_reset_event("codex_resets")
    assert "provider=codex_resets kind=landed reason=disabled in settings" in caplog.text


def test_notification_logging_records_first_run(monkeypatch, caplog):
    caplog.set_level("INFO", logger="aigauge.app")
    app, providers, saves = make_app(monkeypatch, tray=Mock())
    app._config.codex_resets.last_event_key = None
    providers["codex_resets"].latest_event = event("landed", "new", "codex")
    app._on_reset_event("codex_resets")
    saves.assert_called_once_with()
    assert "provider=codex_resets reason=first run, recorded without notification" in caplog.text


def test_first_event_is_recorded_without_notification_and_duplicates_are_ignored(
    monkeypatch,
):
    tray = Mock()
    app, providers, saves = make_app(monkeypatch, tray=tray)
    app._config.codex_resets.last_event_key = None
    providers["codex_resets"].latest_event = event("landed", "new", "codex")
    app._on_reset_event("codex_resets")
    app._on_reset_event("codex_resets")
    assert app._config.codex_resets.last_event_key == "landed:new"
    saves.assert_called_once_with()
    tray.showMessage.assert_not_called()


def test_same_id_announced_then_landed_queues_two_notifications(monkeypatch):
    tray = Mock()
    app, providers, _ = make_app(monkeypatch, tray=tray)
    timers = []
    clock = [0.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        app_module.QTimer, "singleShot", lambda delay, callback: timers.append(
            (delay, callback)
        )
    )
    providers["codex_resets"].latest_event = event(
        "announced", "same", "codex"
    )
    app._on_reset_event("codex_resets")
    providers["codex_resets"].latest_event = event("landed", "same", "codex")
    app._on_reset_event("codex_resets")
    assert tray.showMessage.call_count == 1
    assert app._config.codex_resets.last_event_key == "landed:same"
    clock[0] += app_module._RESET_NOTIFICATION_SPACING_MS / 1000
    timers.pop()[1]()
    assert tray.showMessage.call_count == 2


def test_disabled_kind_is_not_enqueued_and_event_is_still_recorded(monkeypatch):
    tray = Mock()
    app, providers, saves = make_app(monkeypatch, tray=tray)
    app._config.codex_resets.notify_landed = False
    providers["codex_resets"].latest_event = event("landed", "new", "codex")
    app._on_reset_event("codex_resets")
    assert app._config.codex_resets.last_event_key == "landed:new"
    saves.assert_called_once_with()
    tray.showMessage.assert_not_called()


def test_missing_or_unavailable_tray_does_not_raise(monkeypatch):
    app, providers, _ = make_app(monkeypatch)
    providers["codex_resets"].latest_event = event("landed", "one", "codex")
    app._on_reset_event("codex_resets")
    tray = Mock()
    app._tray = tray
    monkeypatch.setattr(
        QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False)
    )
    providers["claude_resets"].latest_event = event("landed", "two", "claude")
    app._on_reset_event("claude_resets")
    tray.showMessage.assert_not_called()
