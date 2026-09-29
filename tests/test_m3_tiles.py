from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aigauge.app import App
from aigauge.config import Config
from aigauge.models import SnapshotStatus, UsageMetric, UsageSnapshot
from aigauge.providers._resets_common import (
    ResetEvent, ResetWatch, ResetsFetchError, build_snapshot,
)
from aigauge.providers.codex_resets import CodexResetsProvider, _parse_watch
from aigauge.widget import UsageWidget, _SummaryChip


NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)


def watch_payload(source=None, **changes):
    payload = {
        "level": "elevated",
        "reset_chance_percent": 37,
        "forecast_window": "later this week",
        "observed_at": "2026-09-27T11:00:00Z",
        "expires_at": "2026-09-29T11:00:00Z",
        "text": "Synthetic activity suggests a possible reset.",
        "source": source if source is not None else {"type": "observed"},
    }
    payload.update(changes)
    return payload


def event(identifier="one"):
    return ResetEvent(
        "landed", identifier, NOW, "limits refilled", "Synthetic event",
        f"https://example.test/{identifier}",
    )


def ag_snapshot(groups=("Gemini", "Claude+GPT")):
    return UsageSnapshot(
        provider="antigravity", status=SnapshotStatus.OK,
        metrics=[
            UsageMetric(f"{group} {window}", percent, None,
                        reset_label="idle" if window == "5h" else "2.8d")
            for group in groups
            for window, percent in (("5h", 0.0), ("weekly", 14.0))
        ],
    )


def test_antigravity_compact_groups_and_saved_state(qtbot, monkeypatch):
    config = Config()
    save = Mock()
    monkeypatch.setattr(Config, "save", save)
    widget = UsageWidget(config)
    qtbot.addWidget(widget)
    widget.update_snapshot(ag_snapshot(), "Antigravity")
    tile = widget._tiles["antigravity"]
    assert not tile.expand_btn.isHidden()
    assert tile._expanded
    app = App.__new__(App)
    app._config = config
    tile.expand_btn.click()
    assert tile.expand_btn.text() == "▸"
    assert tile._compact_below_header
    assert tile._rows == []
    assert [row.layout().itemAt(0).widget().text() for row in tile._compact_group_rows] == [
        "Gemini", "Claude+GPT",
    ]
    assert [item.code.text() for item in tile._compact_metrics] == ["5", "W", "5", "W"]
    tile.set_available_width(320)
    assert all(row.sizeHint().width() <= 320 for row in tile._compact_group_rows)
    assert tile._compact_group_rows[0].layout().itemAt(1).widget().x() == (
        tile._compact_group_rows[1].layout().itemAt(1).widget().x()
    )
    app._on_tile_expanded_changed("antigravity", False)
    assert config.collapsed_tiles == ["antigravity"]
    save.assert_called_once()
    widget.update_snapshot(ag_snapshot(("Claude+GPT",)), "Antigravity")
    assert len(tile._compact_group_rows) == 1
    assert [item.code.text() for item in tile._compact_metrics] == ["5", "W"]
    widget.update_snapshot(ag_snapshot(()), "Antigravity")
    assert tile._compact_summary.isHidden()


@pytest.mark.parametrize("name,codes", [
    ("claude", ["S", "W"]), ("codex", ["S", "W"]),
    ("opencode_go", ["R", "M"]),
])
def test_other_compact_tiles_keep_header_chips(qtbot, name, codes):
    widget = UsageWidget(Config())
    qtbot.addWidget(widget)
    labels = ("Rolling", "Monthly") if name == "opencode_go" else ("Session", "Weekly")
    widget.update_snapshot(UsageSnapshot(
        provider=name, status=SnapshotStatus.OK,
        metrics=[UsageMetric(label, 20.0, None) for label in labels],
    ), name)
    tile = widget._tiles[name]
    tile.set_expanded(False)
    assert not tile._compact_below_header
    assert tile._rows == []
    assert [item.code.text() for item in tile._compact_metrics] == codes


@pytest.mark.parametrize("name", ["codex_resets", "claude_resets"])
def test_dismissed_tile_hides_on_ok_and_error_then_returns(qtbot, name):
    widget = UsageWidget(Config())
    qtbot.addWidget(widget)
    first = event()
    for error in (None, "HTTP 503"):
        widget.update_snapshot(build_snapshot(name, first, first.key, NOW, error), name)
        assert widget._tiles[name].isHidden()
        assert name in widget._tiles
        widget.set_collapsed(True)
        assert all(
            name.replace("_", " ").lower() not in chip.text().lower()
            for chip in widget._collapsed_widget.findChildren(_SummaryChip)
        )
        widget.set_collapsed(False)
    widget.update_snapshot(build_snapshot(name, event("two"), first.key, NOW), name)
    assert not widget._tiles[name].isHidden()
    widget.update_snapshot(build_snapshot(name, None, None, NOW), name)
    assert not widget._tiles[name].isHidden()
    assert "no new announcements" in widget._tiles[name].status.text()


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


def test_watch_display_expiry_elision_and_url(qtbot, monkeypatch):
    from aigauge import widget as widget_module

    widget = UsageWidget(Config())
    qtbot.addWidget(widget)
    forecast = "a very long synthetic forecast window " * 12
    source_url = "https://example.test/watch"
    watch = _parse_watch(watch_payload(
        {"type": "observed", "url": source_url},
        forecast_window=forecast,
    ))
    snapshot = build_snapshot("codex_resets", None, None, NOW, watch=watch)
    widget.update_snapshot(snapshot, "Codex Resets")
    tile = widget._tiles["codex_resets"]
    tile.set_available_width(320)
    row = tile._rows[0]
    assert row.label.text() == "Watch"
    assert "…" in row.reset.text()
    assert forecast in row.toolTip()
    assert "not an official announcement" in row.toolTip()
    assert not tile.open_btn.isHidden()
    opened = Mock()
    monkeypatch.setattr(widget_module.QDesktopServices, "openUrl", opened)
    tile.open_btn.click()
    assert opened.call_args.args[0].toString() == source_url
    no_url = _parse_watch(watch_payload())
    widget.update_snapshot(build_snapshot("codex_resets", None, None, NOW, watch=no_url), "Codex Resets")
    assert tile.open_btn.isHidden()
    expired = build_snapshot("codex_resets", None, None, NOW + timedelta(days=3), watch=watch)
    widget.update_snapshot(expired, "Codex Resets")
    assert tile._rows == []
    assert not tile.isHidden()
    assert "no new announcements" in tile.status.text()


def test_watch_null_chance_and_event_dismissal(qtbot):
    watch = _parse_watch(watch_payload(reset_chance_percent=None))
    snapshot = build_snapshot("codex_resets", event(), event().key, NOW, watch=watch)
    assert len(snapshot.metrics) == 1
    assert snapshot.metrics[0].label == "Watch · elevated · later this week (AI)"
    widget = UsageWidget(Config())
    qtbot.addWidget(widget)
    widget.update_snapshot(snapshot, "Codex Resets")
    assert widget._tiles["codex_resets"]._rows[0].label.text() == "Watch"


def test_event_row_precedes_watch_and_event_url_wins(qtbot, monkeypatch):
    from aigauge import widget as widget_module

    watch = _parse_watch(watch_payload(
        {"type": "observed", "url": "https://example.test/watch"}
    ))
    widget = UsageWidget(Config())
    qtbot.addWidget(widget)
    widget.update_snapshot(build_snapshot("codex_resets", event(), None, NOW, watch=watch),
                           "Codex Resets")
    tile = widget._tiles["codex_resets"]
    assert [row.label.text() for row in tile._rows] == ["Reset", "Watch"]
    opened = Mock()
    monkeypatch.setattr(widget_module.QDesktopServices, "openUrl", opened)
    tile.open_btn.click()
    assert opened.call_args.args[0].toString() == event().url


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
