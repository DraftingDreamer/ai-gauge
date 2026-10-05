from datetime import datetime, timedelta

from aigauge.models import SnapshotStatus
from aigauge.providers.codex import (
    CODEX_USAGE_URL,
    EXTRACTOR_JS,
    _build_snapshot,
    _parse_reset_text,
)


def test_parse_reset_text_handles_weekday_time():
    parsed = _parse_reset_text("Mon 6:00 PM")

    assert parsed is not None
    assert parsed.weekday() == 0
    assert parsed.hour == 18
    assert parsed.minute == 0
    assert parsed > datetime.now()


def test_parse_reset_text_handles_at_prefix_and_date_at_time():
    time_only = _parse_reset_text("at 4:47 PM")
    dated = _parse_reset_text("May 19, 2026 at 9:36 AM")

    assert time_only is not None
    assert time_only.hour == 16
    assert time_only.minute == 47
    assert dated is not None
    assert dated.month == 5
    assert dated.day == 19
    assert dated.year == 2026
    assert dated.hour == 9
    assert dated.minute == 36


def test_codex_logged_out_payload_is_auth_required():
    snapshot = _build_snapshot(
        {
            "logged_out": True,
            "session": None,
            "weekly": None,
            "title": "Login",
            "body_text": "Sign in to continue",
        }
    )

    assert snapshot.status == SnapshotStatus.AUTH_REQUIRED
    assert "Not signed in" in (snapshot.error or "")


def test_codex_empty_shell_with_login_task_titles_is_transient_error():
    snapshot = _build_snapshot(
        {
            "logged_out": True,
            "session": None,
            "weekly": None,
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "Codex cloud tasks Sign in flow debugging",
        }
    )

    assert snapshot.status == SnapshotStatus.ERROR
    assert "without usage cards" in (snapshot.error or "")


def test_codex_usage_rows_ignore_stale_logged_out_flag():
    snapshot = _build_snapshot(
        {
            "logged_out": True,
            "session": {"percent": 12, "kind": "used", "reset_text": "4 hr 10 min"},
            "weekly": {"percent": 31, "kind": "used", "reset_text": "Mon 6:00 PM"},
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "Codex Tasks Sign in debugging 5 hour usage limit 12% used",
        }
    )

    assert snapshot.status == SnapshotStatus.OK
    assert [metric.label for metric in snapshot.metrics] == ["Session", "Weekly"]


def test_codex_cloudflare_payload_is_auth_required():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": None,
            "weekly": None,
            "title": "Just a moment...",
            "body_text": "Verify you are human Cloudflare",
        }
    )

    assert snapshot.status == SnapshotStatus.AUTH_REQUIRED
    assert "security verification" in (snapshot.error or "")


def test_codex_cloudflare_soft_payload_is_auth_required():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": None,
            "weekly": None,
            "title": "Just a moment...",
            "body_text": "Checking if the site connection is secure. Cloudflare",
        }
    )

    assert snapshot.status == SnapshotStatus.AUTH_REQUIRED
    assert "security verification" in (snapshot.error or "")


def test_codex_usage_rows_ignore_cloudflare_mentions():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": {"percent": 12, "kind": "used", "reset_text": "4 hr 10 min"},
            "weekly": {"percent": 31, "kind": "used", "reset_text": "Mon 6:00 PM"},
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": (
                "Codex Tasks Cloudflare tunnel debugging 5 hour usage limit 12% used "
                "Weekly usage limit 31% used"
            ),
        }
    )

    assert snapshot.status == SnapshotStatus.OK
    assert [metric.label for metric in snapshot.metrics] == ["Session", "Weekly"]


def test_codex_body_text_fallback_ignores_cloudflare_task_titles():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": None,
            "weekly": None,
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": (
                "Codex Tasks Just a moment Cloudflare tunnel debugging "
                "Personal usage 5 hour usage limit 88% remaining Resets at 4:47 PM "
                "Weekly usage limit 75% remaining Resets Mon 6:00 PM"
            ),
            "has_usage_text": True,
            "has_percent_text": True,
        }
    )

    assert snapshot.status == SnapshotStatus.OK
    assert [metric.percent_used for metric in snapshot.metrics] == [12.0, 25.0]


def test_codex_signed_in_empty_usage_payload_is_transient_error():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": None,
            "weekly": None,
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "Codex cloud tasks",
        }
    )

    assert snapshot.status == SnapshotStatus.ERROR
    assert "without usage cards" in (snapshot.error or "")


def test_codex_session_without_weekly_is_transient_error():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": {
                "percent": 2,
                "kind": "remaining",
                "reset_text": "Jul 10, 2026 12:14 AM",
            },
            "weekly": None,
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "5 hour usage limit 2% remaining Weekly usage limit",
        }
    )

    assert snapshot.status == SnapshotStatus.ERROR
    assert "part of the usage cards" in (snapshot.error or "")


def test_codex_weekly_only_shared_limit_layout_is_supported():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": None,
            "weekly": {
                "percent": 5,
                "kind": "remaining",
                "reset_text": "Jul 20, 2026 7:57 PM",
            },
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": (
                "Balance Codex usage draws from your shared agentic usage limit "
                "Weekly usage limit 5% remaining Resets Jul 20, 2026 7:57 PM "
                "Credits remaining 0 Usage breakdown Personal usage"
            ),
        }
    )

    assert snapshot.status == SnapshotStatus.OK
    assert [metric.label for metric in snapshot.metrics] == ["Weekly"]
    assert snapshot.metrics[0].percent_used == 95.0
    assert snapshot.metrics[0].resets_at == datetime(2026, 7, 20, 19, 57)
    assert snapshot.metrics[0].window == timedelta(days=7)


def test_codex_weekly_only_without_shared_layout_context_is_transient_error():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": None,
            "weekly": {
                "percent": 5,
                "kind": "remaining",
                "reset_text": "Jul 20, 2026 7:57 PM",
            },
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "Weekly usage limit 5% remaining",
        }
    )

    assert snapshot.status == SnapshotStatus.ERROR
    assert "part of the usage cards" in (snapshot.error or "")


def test_codex_extractor_uses_shared_overview_logic():
    assert 'function getCodexPageState()' in EXTRACTOR_JS
    assert 'maybeSelectOverview(bodyText)' in EXTRACTOR_JS
    assert 'aria-pressed' in EXTRACTOR_JS


def test_codex_active_session_with_unused_weekly_limit_is_valid():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": {
                "percent": 98,
                "kind": "remaining",
                "reset_text": "1:34 PM",
            },
            "weekly": {
                "percent": 100,
                "kind": "remaining",
                "reset_text": None,
            },
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": (
                "Balance Codex and Work share the same usage limit. "
                "5 hour usage limit 98% remaining Resets 1:34 PM "
                "Weekly usage limit 100% remaining"
            ),
        }
    )

    assert snapshot.status == SnapshotStatus.OK
    assert [
        (metric.label, metric.percent_used, metric.reset_label)
        for metric in snapshot.metrics
    ] == [
        ("Session", 2.0, None),
        ("Weekly", 0.0, "idle"),
    ]

def test_codex_usage_signal_prevents_false_idle_fallback():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": None,
            "weekly": None,
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "Codex cloud tasks",
            "has_usage_text": True,
        }
    )

    assert snapshot.status == SnapshotStatus.ERROR
    assert "layout may have changed" in (snapshot.error or "")


def test_codex_generic_usage_text_prevents_false_idle_fallback():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": None,
            "weekly": None,
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "Codex cloud Usage Settings",
        }
    )

    assert snapshot.status == SnapshotStatus.ERROR
    assert "layout may have changed" in (snapshot.error or "")


def test_codex_unparsed_usage_payload_still_reports_layout_error():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": None,
            "weekly": None,
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "5 hour usage limit Weekly usage limit",
        }
    )

    assert snapshot.status == SnapshotStatus.ERROR
    assert "layout may have changed" in (snapshot.error or "")


def test_codex_metrics_carry_windows():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": {"percent": 10, "kind": "used", "reset_text": "4 hr 30 min"},
            "weekly": {"percent": 20, "kind": "used", "reset_text": "Mon 6:00 PM"},
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "5 hour usage limit 10% Weekly usage limit 20%",
        }
    )

    assert snapshot.status == SnapshotStatus.OK
    assert [metric.window for metric in snapshot.metrics] == [
        timedelta(hours=5),
        timedelta(days=7),
    ]


def test_codex_body_text_fallback_reads_new_visible_cards():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "session": None,
            "weekly": None,
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": (
                "Personal usage 5 hour usage limit 99% remaining "
                "Resets at 4:47 PM Weekly usage limit 94% remaining "
                "Resets May 19, 2026 at 9:36 AM"
            ),
            "has_usage_text": True,
            "has_percent_text": True,
        }
    )

    assert snapshot.status == SnapshotStatus.OK
    assert [metric.percent_used for metric in snapshot.metrics] == [1.0, 6.0]
    assert all(metric.resets_at is not None for metric in snapshot.metrics)


def test_codex_overview_body_fallback_reads_only_confirmed_weekly_quota():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "overview_confirmed": True,
            "session": None,
            "weekly": None,
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "Usage Overview Weekly limits 5 天 10 小時後重設 剩餘 94%",
        }
    )

    assert snapshot.status == SnapshotStatus.OK
    assert [metric.label for metric in snapshot.metrics] == ["Weekly"]
    assert snapshot.metrics[0].percent_used == 6.0
    assert snapshot.metrics[0].resets_at is not None


def test_codex_overview_weekly_history_is_not_a_quota():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "overview_confirmed": True,
            "weekly": None,
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": (
                "Usage Overview Analytics Usage history Tasks 80.4% Subagents 19.2% "
                "Plan usage history Weekly limits Period % of limit used Sep 21-26 73.9%"
            ),
        }
    )

    assert snapshot.status == SnapshotStatus.ERROR
    assert snapshot.metrics == []


def test_codex_overview_session_heading_without_card_does_not_use_weekly_alone():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "overview_confirmed": True,
            "weekly": {"percent": 94, "kind": "remaining", "reset_text": "5 days 10 hours"},
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "5 hour usage limit Weekly limits 94% remaining",
        }
    )

    assert snapshot.status == SnapshotStatus.ERROR
    assert snapshot.metrics == []


def test_codex_overview_accepts_explicit_idle_boundary_percentages():
    for percent, kind in ((100, "remaining"), (0, "used")):
        snapshot = _build_snapshot(
            {
                "logged_out": False,
                "overview_confirmed": True,
                "weekly": {"percent": percent, "kind": kind, "reset_text": None},
                "title": "Codex",
                "url": CODEX_USAGE_URL,
                "body_text": f"Usage Overview Weekly limits {percent}% {kind}",
            }
        )
        assert snapshot.status == SnapshotStatus.OK
        assert snapshot.metrics[0].percent_used == 0.0


def test_codex_overview_rejects_invalid_or_unknown_percentages():
    for percent, kind in ((101, "used"), (-1, "used"), (12, "unknown")):
        snapshot = _build_snapshot(
            {
                "logged_out": False,
                "overview_confirmed": True,
                "weekly": {"percent": percent, "kind": kind, "reset_text": "2 days"},
                "title": "Codex",
                "url": CODEX_USAGE_URL,
                "body_text": "Usage Overview Weekly limits",
            }
        )
        assert snapshot.status == SnapshotStatus.ERROR
        assert snapshot.metrics == []


def test_codex_relative_reset_parser_accepts_injected_clock_and_chinese_days():
    now = datetime(2026, 10, 4, 9, 0)
    assert _parse_reset_text("5 天 10 小時", now=now) == now + timedelta(hours=130)
    assert _parse_reset_text("in 5 days 10 hours", now=now) == now + timedelta(hours=130)


def test_codex_overview_body_fallback_reads_percent_before_reset_countdown():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "overview_confirmed": True,
            "weekly": None,
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "Usage Overview Weekly limits 94% remaining 5 days 10 hours until reset",
        }
    )

    assert snapshot.status == SnapshotStatus.OK
    assert snapshot.metrics[0].percent_used == 6.0
    assert snapshot.metrics[0].resets_at is not None


def test_codex_overview_keeps_structured_idle_card_when_body_is_truncated():
    snapshot = _build_snapshot(
        {
            "logged_out": False,
            "overview_confirmed": True,
            "weekly": {
                "percent": 100,
                "kind": "remaining",
                "reset_text": None,
                "raw": "Weekly limits 100% remaining",
            },
            "title": "Codex",
            "url": CODEX_USAGE_URL,
            "body_text": "Usage Overview",
        }
    )

    assert snapshot.status == SnapshotStatus.OK
    assert snapshot.metrics[0].percent_used == 0.0
