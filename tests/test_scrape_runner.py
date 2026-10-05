import logging
from typing import Any

import pytest

from aigauge.models import SnapshotStatus, UsageSnapshot
from aigauge.providers import _scrape_runner as runner_module
from aigauge.providers import codex as codex_module
from aigauge.providers._scrape_runner import ScrapeRunner
from aigauge.providers.codex import CodexProvider


class _FakeDoneSignal:
    def __init__(self):
        self._slot = None

    def connect(self, slot):
        self._slot = slot

    def emit(self, result, error):
        assert self._slot is not None, "no slot connected"
        self._slot(result, error)


class _FakeScraper:
    """Stand-in for HeadlessScraper that fires `done` synchronously on demand."""

    instances: list["_FakeScraper"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.done = _FakeDoneSignal()
        _FakeScraper.instances.append(self)


@pytest.fixture
def fake_scraper(monkeypatch):
    _FakeScraper.instances.clear()
    monkeypatch.setattr(runner_module, "HeadlessScraper", _FakeScraper)
    # The runner refuses to scrape when QtWebEngine is unusable, and the test
    # environment (offscreen platform) genuinely has no GL context. These tests
    # drive a fake scraper, so declare the real thing available.
    monkeypatch.setattr(runner_module.webengine, "is_available", lambda: True)
    yield _FakeScraper
    _FakeScraper.instances.clear()


def _ok_snapshot() -> UsageSnapshot:
    return UsageSnapshot(provider="x", status=SnapshotStatus.OK)


def _err_snapshot(reason: str = "layout") -> UsageSnapshot:
    return UsageSnapshot(provider="x", status=SnapshotStatus.ERROR, error=reason)


def test_scrape_runner_passes_ok_snapshot_through(fake_scraper):
    received: list[UsageSnapshot] = []
    rn = ScrapeRunner(
        account_id="x",
        url="http://example",
        extractor_js="",
        build=lambda payload: _ok_snapshot(),
        log=logging.getLogger("test"),
        build_max_attempts=2,
    )
    rn.run(received.append)

    assert len(fake_scraper.instances) == 1
    fake_scraper.instances[0].done.emit({"any": "payload"}, "")

    assert len(received) == 1
    assert received[0].status == SnapshotStatus.OK
    # No retry should have been scheduled.
    assert len(fake_scraper.instances) == 1


def test_scrape_runner_retries_on_build_error(fake_scraper):
    received: list[UsageSnapshot] = []
    calls: list[dict[str, Any]] = []

    def _build(payload):
        calls.append(payload)
        # First call fails, second succeeds — mirrors the partial-render
        # scenario that motivated the runner.
        return _err_snapshot() if len(calls) == 1 else _ok_snapshot()

    rn = ScrapeRunner(
        account_id="x",
        url="http://example",
        extractor_js="",
        build=_build,
        log=logging.getLogger("test"),
        build_max_attempts=2,
    )
    rn.run(received.append)

    fake_scraper.instances[0].done.emit({"first": True}, "")
    assert received == [], "first ERROR should trigger retry, not deliver"
    assert len(fake_scraper.instances) == 2, "second scrape should have started"

    fake_scraper.instances[1].done.emit({"second": True}, "")
    assert len(received) == 1
    assert received[0].status == SnapshotStatus.OK


def test_scrape_runner_stops_retrying_after_limit(fake_scraper):
    received: list[UsageSnapshot] = []
    rn = ScrapeRunner(
        account_id="x",
        url="http://example",
        extractor_js="",
        build=lambda payload: _err_snapshot("layout"),
        log=logging.getLogger("test"),
        build_max_attempts=2,
    )
    rn.run(received.append)

    fake_scraper.instances[0].done.emit({}, "")
    fake_scraper.instances[1].done.emit({}, "")

    assert len(fake_scraper.instances) == 2, "should not retry past build_max_attempts"
    assert len(received) == 1
    assert received[0].status == SnapshotStatus.ERROR


def test_codex_empty_analytics_payload_retries_then_returns_weekly_usage(fake_scraper):
    """An analytics shell without cards gets one bounded whole-page retry."""
    from aigauge.providers.codex import _build_snapshot

    received: list[UsageSnapshot] = []
    rn = ScrapeRunner(
        account_id="codex-work",
        url="https://chatgpt.com/settings/usage",
        extractor_js="extract",
        build=lambda payload: _build_snapshot(payload, account_id="codex-work"),
        log=logging.getLogger("test"),
        build_max_attempts=2,
    )
    rn.run(received.append)

    fake_scraper.instances[0].done.emit(
        {
            "logged_out": False,
            "session": None,
            "weekly": None,
            "title": "Codex",
            "url": "https://chatgpt.com/settings/usage",
            "body_text": "Codex cloud tasks",
            "overview_confirmed": False,
        },
        "",
    )
    assert received == []
    assert len(fake_scraper.instances) == 2

    fake_scraper.instances[1].done.emit(
        {
            "logged_out": False,
            "session": None,
            "weekly": {"percent": 37, "kind": "used", "reset_text": "Mon 6:00 PM"},
            "title": "Codex",
            "url": "https://chatgpt.com/settings/usage",
            "body_text": "Usage Overview Weekly limits 37% used Resets Mon 6:00 PM",
            "overview_confirmed": True,
            "overview_ready": True,
        },
        "",
    )

    assert len(received) == 1
    assert received[0].provider == "codex-work"
    assert received[0].status == SnapshotStatus.OK
    assert [(metric.label, metric.percent_used) for metric in received[0].metrics] == [
        ("Weekly", 37)
    ]


def test_codex_refresh_uses_cache_busted_overview_url(monkeypatch):
    captured = {}

    class Runner:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self, on_done):
            captured["on_done"] = on_done

    monkeypatch.setattr(codex_module, "ScrapeRunner", Runner)
    CodexProvider(account_id="codex-work").refresh(lambda _snapshot: None)

    url = captured["url"]
    assert url.startswith("https://chatgpt.com/settings/usage?")
    assert "aigauge_ts=" in url
    assert "/codex/cloud/settings/analytics" not in url
    assert "#personal-usage" not in url
    assert captured["account_id"] == "codex-work"


def test_scrape_runner_surfaces_transport_error_without_build(fake_scraper):
    received: list[UsageSnapshot] = []
    build_calls = []
    rn = ScrapeRunner(
        account_id="x",
        url="http://example",
        extractor_js="",
        build=lambda payload: (build_calls.append(payload), _ok_snapshot())[1],
        log=logging.getLogger("test"),
        build_max_attempts=2,
    )
    rn.run(received.append)

    fake_scraper.instances[0].done.emit(None, "timeout")

    assert build_calls == [], "build should be skipped on transport error"
    assert len(received) == 1
    assert received[0].status == SnapshotStatus.ERROR
    assert received[0].error == "timeout"


def test_scrape_runner_reports_error_when_webengine_is_unavailable(monkeypatch):
    """Regression for issue #7.

    On a session with no GL context Chromium cannot start. The runner must say
    so on the provider tile rather than importing WebEngine and taking the
    process down with it.
    """
    _FakeScraper.instances.clear()
    monkeypatch.setattr(runner_module, "HeadlessScraper", _FakeScraper)
    monkeypatch.setattr(runner_module.webengine, "is_available", lambda: False)
    monkeypatch.setattr(
        runner_module.webengine, "unavailable_reason", lambda: "no GLX/EGL"
    )

    received: list[UsageSnapshot] = []
    rn = ScrapeRunner(
        account_id="claude",
        url="http://example",
        extractor_js="",
        build=lambda payload: _ok_snapshot(),
        log=logging.getLogger("test"),
    )
    rn.run(received.append)

    assert _FakeScraper.instances == [], "no browser should be started"
    assert len(received) == 1
    assert received[0].status == SnapshotStatus.ERROR
    assert "no GLX/EGL" in received[0].error
