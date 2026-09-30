from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtWidgets import QSystemTrayIcon

from aigauge import app as app_module
from aigauge import windows_toast
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
    monkeypatch.setattr(app_module, "sys", SimpleNamespace(platform="linux"))
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


def test_two_windows_toasts_are_sent_immediately_without_tray_queue(
    monkeypatch, caplog,
):
    show_toast = Mock(return_value=True)
    monkeypatch.setattr(windows_toast, "show_toast", show_toast)
    tray = Mock()
    app, providers, _ = make_app(monkeypatch, tray=tray)
    monkeypatch.setattr(app_module, "sys", SimpleNamespace(platform="win32"))
    clock = Mock(return_value=100.0)
    monkeypatch.setattr(app_module.time, "monotonic", clock)
    single_shot = Mock()
    monkeypatch.setattr(app_module.QTimer, "singleShot", single_shot)
    caplog.set_level("INFO", logger="aigauge.app")

    providers["codex_resets"].latest_event = event("landed", "codex", "codex")
    providers["claude_resets"].latest_event = event("landed", "claude", "claude")
    app._on_reset_event("codex_resets")
    app._on_reset_event("claude_resets")

    assert [call.args[2] for call in show_toast.call_args_list] == [
        "https://example.test/codex/codex/landed",
        "https://example.test/claude/claude/landed",
    ]
    assert show_toast.call_count == 2
    assert caplog.text.count("via=toast") == 2
    single_shot.assert_not_called()
    clock.assert_not_called()
    tray.showMessage.assert_not_called()


def test_toast_success_does_not_delay_following_tray_fallback(monkeypatch):
    show_toast = Mock(side_effect=[True, False])
    monkeypatch.setattr(windows_toast, "show_toast", show_toast)
    tray = Mock()
    app, providers, _ = make_app(monkeypatch, tray=tray)
    monkeypatch.setattr(app_module, "sys", SimpleNamespace(platform="win32"))
    single_shot = Mock()
    monkeypatch.setattr(app_module.QTimer, "singleShot", single_shot)

    providers["codex_resets"].latest_event = event("landed", "toast", "codex")
    providers["claude_resets"].latest_event = event("landed", "tray", "claude")
    app._on_reset_event("codex_resets")
    app._on_reset_event("claude_resets")

    assert show_toast.call_count == 2
    tray.showMessage.assert_called_once()
    assert app._last_reset_notification_url == (
        "https://example.test/claude/tray/landed"
    )
    single_shot.assert_not_called()


def test_tray_spacing_does_not_delay_following_successful_toast(monkeypatch):
    tray = Mock()
    app, providers, _ = make_app(monkeypatch, tray=tray)
    clock = [50.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    single_shot = Mock()
    monkeypatch.setattr(app_module.QTimer, "singleShot", single_shot)
    providers["codex_resets"].latest_event = event("landed", "tray", "codex")
    app._on_reset_event("codex_resets")
    tray.showMessage.assert_called_once()

    monkeypatch.setattr(app_module, "sys", SimpleNamespace(platform="win32"))
    show_toast = Mock(return_value=True)
    monkeypatch.setattr(windows_toast, "show_toast", show_toast)
    providers["claude_resets"].latest_event = event("landed", "toast", "claude")
    app._on_reset_event("claude_resets")

    show_toast.assert_called_once_with(
        "Claude reset landed", "Usage limits were refilled. Click to open the post.",
        "https://example.test/claude/toast/landed",
    )
    single_shot.assert_not_called()
    tray.showMessage.assert_called_once()


def test_failed_toast_is_not_retried_when_queued_tray_notice_is_shown(monkeypatch):
    tray = Mock()
    app, providers, _ = make_app(monkeypatch, tray=tray)
    clock = [100.0]
    monkeypatch.setattr(app_module.time, "monotonic", lambda: clock[0])
    timers = []
    monkeypatch.setattr(
        app_module.QTimer, "singleShot", lambda delay, callback: timers.append(
            (delay, callback)
        )
    )
    providers["codex_resets"].latest_event = event("landed", "first", "codex")
    app._on_reset_event("codex_resets")

    monkeypatch.setattr(app_module, "sys", SimpleNamespace(platform="win32"))
    show_toast = Mock(return_value=False)
    monkeypatch.setattr(windows_toast, "show_toast", show_toast)
    providers["claude_resets"].latest_event = event("landed", "second", "claude")
    app._on_reset_event("claude_resets")
    assert show_toast.call_count == 1
    assert len(timers) == 1
    assert timers[0][0] == app_module._RESET_NOTIFICATION_SPACING_MS

    clock[0] += app_module._RESET_NOTIFICATION_SPACING_MS / 1000
    timers.pop()[1]()
    assert show_toast.call_count == 1
    assert tray.showMessage.call_count == 2


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


def test_notification_messages_omit_open_post_hint_without_url(monkeypatch):
    expected = {
        "announced": (
            "Codex reset announced",
            "A regular reset was announced.",
        ),
        "landed": (
            "Codex reset landed",
            "Usage limits were refilled.",
        ),
        "banked": (
            "Codex reset credit granted",
            "A banked reset is available to redeem in Codex.",
        ),
    }
    app, providers, _ = make_app(monkeypatch, tray=Mock())
    enqueue = Mock()
    app._enqueue_reset_notification = enqueue

    for kind, (title, message) in expected.items():
        for url in ("https://example.test/post", None):
            providers["codex_resets"].latest_event = ResetEvent(
                kind, f"{kind}-{bool(url)}", NOW, "regular reset", "detail", url
            )
            app._on_reset_event("codex_resets")
            complete_message = message + (
                " Click to open the post." if url is not None else ""
            )
            assert enqueue.call_args.args[:3] == (title, complete_message, url)
