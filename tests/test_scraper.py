from typing import Any, cast

from aigauge.webview.scraper import HeadlessScraper
from PyQt6.QtCore import QUrl


class _LoginPage:
    def url(self):
        return QUrl("https://claude.ai/login")

    def title(self):
        return "Claude"


class _FailedLoginScrape:
    _provider = "claude"
    _finished = False
    _max_progress = 100
    _last_load_status = "LoadStartedStatus"
    _last_load_is_error_page = False
    _page: Any = _LoginPage()

    def __init__(self):
        self.result = None

    def _finish(self, payload, error):
        self.result = (payload, error)


def test_failed_load_on_claude_login_reports_auth_instead_of_transport_failure():
    scrape = _FailedLoginScrape()
    HeadlessScraper._on_load_finished(cast(Any, scrape), False)
    assert scrape.result == ({"logged_out": True, "url": "https://claude.ai/login"}, "")


def test_failed_load_on_sign_in_page_at_new_route_reports_auth():
    scrape = _FailedLoginScrape()
    scrape._page = type("Page", (), {
        "url": lambda self: QUrl("https://claude.ai/new#settings/usage"),
        "title": lambda self: "Sign in - Claude",
    })()
    HeadlessScraper._on_load_finished(cast(Any, scrape), False)
    assert scrape.result == ({"logged_out": True, "url": "https://claude.ai/new"}, "")


def test_failed_load_on_other_page_remains_transport_failure():
    scrape = _FailedLoginScrape()
    scrape._page = type("Page", (), {
        "url": lambda self: QUrl("https://claude.ai/new"),
        "title": lambda self: "Claude",
    })()
    HeadlessScraper._on_load_finished(cast(Any, scrape), False)
    assert scrape.result == (None, "page failed to load")


def test_extractor_retry_limit_is_retryable_transport_error():
    assert "extractor retry limit exceeded" in HeadlessScraper._RETRYABLE_ERRORS


def test_extractor_retry_delay_is_capped(monkeypatch):
    scheduled = []
    monkeypatch.setattr(
        "aigauge.webview.scraper.QTimer.singleShot",
        lambda delay, callback: scheduled.append((delay, callback)),
    )
    page = type(
        "Page",
        (),
        {
            "url": lambda self: "https://chatgpt.com/settings/usage",
            "title": lambda self: "ChatGPT",
        },
    )()
    scrape = type(
        "Scrape",
        (),
        {
            "_finished": False,
            "_provider": "codex",
            "_extractor_reruns": 0,
            "_page": page,
            "_run_extractor": lambda self: None,
        },
    )()

    HeadlessScraper._on_js_result(cast(Any, scrape), {"__retry_after_ms": 60_000})

    assert scheduled[0][0] == 5000
    assert scrape._extractor_reruns == 1
