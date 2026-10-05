from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Callable

from PyQt6.QtCore import QObject

from ..models import SnapshotStatus, UsageMetric, UsageSnapshot
from ._common import (
    has_usage_page_signal,
    is_security_verification_page,
    normalize_percent,
)
from ._codex_page import CODEX_USAGE_URL, EXTRACTOR_JS, VERIFY_JS
from ._scrape_runner import ScrapeRunner
from .base import Provider
from .diagnostics import log_page_diagnosis
from .idle import idle_reset_state

CODEX_ANALYTICS_URL = "https://chatgpt.com/codex/cloud/settings/analytics"
_EXPECTED_ROWS = ("session", "weekly")
log = logging.getLogger("aigauge.providers.codex")


_WEEKDAYS = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


def _parse_reset_text(text: str | None, *, now: datetime | None = None) -> datetime | None:
    """Best-effort parse of strings like 'Mon 6:00 PM', '1:55 PM', or '2h 59m'."""
    if not text:
        return None
    text = text.strip().rstrip(".")
    text = re.sub(r"^at\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^in\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+at\s+", " ", text, count=1, flags=re.IGNORECASE)
    now = now or datetime.now()

    # Relative countdowns in the current Overview card can include days and
    # Traditional Chinese units, for example "5 天 10 小時".
    relative = re.fullmatch(
        r"\s*(?:(\d+)\s*(?:days?|d|天))?\s*"
        r"(?:(\d+)\s*(?:hours?|hrs?|h|小時|小时))?\s*"
        r"(?:(\d+)\s*(?:minutes?|mins?|min|m|分鐘|分钟))?\s*",
        text,
        re.IGNORECASE,
    )
    if relative and any(relative.groups()):
        days, hours, minutes = (int(value or 0) for value in relative.groups())
        return now + timedelta(days=days, hours=hours, minutes=minutes)

    # Relative: "in 2 hr 59 min", "2h 59m", "6 hr 29 min"
    rel = re.match(
        r"(?:in\s+)?(?:(\d+)\s*(?:hr|h|hour)s?)?\s*(?:(\d+)\s*(?:min|m|minute)s?)?",
        text,
        re.IGNORECASE,
    )
    if rel and (rel.group(1) or rel.group(2)):
        hours = int(rel.group(1) or 0)
        minutes = int(rel.group(2) or 0)
        if hours or minutes:
            return now + timedelta(hours=hours, minutes=minutes)

    # Absolute date+time: "Apr 29, 2026 8:53 AM"
    for fmt in ("%b %d, %Y %I:%M %p", "%b %d %I:%M %p", "%B %d, %Y %I:%M %p"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    # Weekday + time: "Mon 6:00 PM", "Monday 18:00" → next matching weekday.
    weekday_match = re.match(r"([A-Za-z]+)\s+(.+)$", text)
    if weekday_match:
        weekday = _WEEKDAYS.get(weekday_match.group(1).lower())
        time_text = weekday_match.group(2).strip()
        if weekday is not None:
            for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M"):
                try:
                    t = datetime.strptime(time_text, fmt).time()
                    days_ahead = (weekday - now.weekday()) % 7
                    candidate = datetime.combine(
                        now.date() + timedelta(days=days_ahead),
                        t,
                    )
                    if candidate <= now:
                        candidate += timedelta(days=7)
                    return candidate
                except ValueError:
                    continue

    # Time-of-day only: "1:55 PM" → today (or tomorrow if past)
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M"):
        try:
            t = datetime.strptime(text, fmt).time()
            candidate = datetime.combine(now.date(), t)
            if candidate < now:
                candidate += timedelta(days=1)
            return candidate
        except ValueError:
            continue

    return None


def _is_codex_analytics_url(url: str) -> bool:
    normalized = url.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
    return normalized in (CODEX_ANALYTICS_URL, CODEX_USAGE_URL)


def _payload_has_usage_signal(payload: dict[str, Any]) -> bool:
    if bool(payload.get("has_percent_text")) or bool(payload.get("has_usage_text")):
        return True
    page_text = f"{payload.get('title', '')} {payload.get('body_text', '')}".lower()
    return "%" in page_text or "usage limit" in page_text or "usage" in page_text


def _clean_reset_text(text: str) -> str | None:
    """Stop a reset timestamp before the adjacent quota value or direction."""
    return re.split(
        r"\s*(?:\d+(?:\.\d+)?\s*%|\b(?:remaining|left|used)\b|已使用|已用|剩餘|尚餘)",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip() or None


def _parse_body_card(
    body_text: str,
    label: str,
    next_labels: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    text = re.sub(r"\s+", " ", body_text or "").strip()
    lower_text = text.lower()
    start = lower_text.find(label.lower())
    if start < 0:
        return None

    end = len(text)
    quota_labels = ("5 hour usage limit", "Weekly usage limit", "Weekly limits", "Weekly limit", "每週上限")
    for next_label in (*next_labels, *quota_labels):
        candidate = lower_text.find(next_label.lower(), start + len(label))
        if candidate >= 0:
            end = min(end, candidate)
    window = text[start:end].strip()
    pct_match = re.search(r"(?<![\d.+-])(\d+(?:\.\d+)?)\s*%", window)
    if not pct_match:
        return None
    percent = float(pct_match.group(1))
    if not 0 <= percent <= 100:
        return None

    reset_match = re.search(
        r"Resets?\s+(?:(?:at|on|in)\s+)?(.+?)(?=\s*$|\s+(?:Daily|Weekly|All|Current|Personal|Team|5 hour)\b|\s+\d+(?:\.\d+)?\s*%)",
        window,
        re.IGNORECASE,
    )
    remaining = re.search(r"\b(?:remaining|left)\b|剩餘|尚餘", window, re.IGNORECASE)
    used = re.search(r"\bused\b|已用|已使用", window, re.IGNORECASE)
    if not remaining and not used:
        return None
    return {
        "raw": window[:400],
        "percent": percent,
        "kind": "remaining" if remaining else ("used" if used else "unknown"),
        "reset_text": _clean_reset_text(reset_match.group(1)) if reset_match else None,
    }


def _parse_overview_weekly(body_text: str) -> dict[str, Any] | None:
    """Read a weekly card only when its Overview copy includes reset semantics."""
    text = re.sub(r"\s+", " ", body_text or "").strip()
    pattern = re.compile(r"(?:Weekly limits?|每週上限)(.{0,500})", re.IGNORECASE)
    stops = re.compile(
        r"(?:5 hour usage limit|Plan usage history|Usage history|Analytics|Period|Tasks|Subagents|"
        r"使用歷史|分析|期間|每日使用量)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        tail = text[match.start() : match.end()]
        stop = stops.search(tail)
        if stop:
            tail = tail[: stop.start()]
        percent_match = re.search(r"(?<![\d.+-])(\d+(?:\.\d+)?)\s*%", tail)
        if not percent_match:
            continue
        percent = float(percent_match.group(1))
        if not 0 <= percent <= 100:
            continue
        if re.search(r"\b(?:remaining|left)\b|剩餘|尚餘", tail, re.IGNORECASE):
            kind = "remaining"
        elif re.search(r"\bused\b|已用|已使用", tail, re.IGNORECASE):
            kind = "used"
        else:
            continue
        reset_match = re.search(
            r"(?:until\s+reset|resets?\s+(?:at|on|in)?|後\s*重設|後\s*重置)",
            tail,
            re.IGNORECASE,
        )
        relative_match = re.search(
            r"(?:\d+\s*(?:days?|d|天)(?:\s*\d+\s*(?:hours?|hrs?|h|小時|小时))?"
            r"(?:\s*\d+\s*(?:minutes?|mins?|min|m|分鐘|分钟))?|"
            r"\d+\s*(?:hours?|hrs?|h|小時|小时)(?:\s*\d+\s*(?:minutes?|mins?|min|m|分鐘|分钟))?|"
            r"\d+\s*(?:minutes?|mins?|min|m|分鐘|分钟))",
            tail,
            re.IGNORECASE,
        )
        idle_quota = (kind == "remaining" and percent == 100) or (
            kind == "used" and percent == 0
        ) or re.search(r"starts? when (?:you )?use|開始使用", tail, re.IGNORECASE)
        if not reset_match and not idle_quota:
            continue
        reset_text = relative_match.group(0).strip() if relative_match else ""
        if not reset_text:
            # English absolute reset labels retain their text for the legacy
            # date parser; Overview currently uses relative countdowns.
            reset_text = re.sub(
                r"^.*?(?:until\s+reset|resets?\s+(?:at|on|in)?|後\s*重設|後\s*重置)\s*",
                "",
                tail,
                flags=re.IGNORECASE,
            ).strip()
        return {
            "raw": tail[:400],
            "percent": percent,
            "kind": kind,
            "reset_text": _clean_reset_text(reset_text),
        }
    return None


def _looks_like_empty_signed_in_usage(payload: dict[str, Any]) -> bool:
    url = str(payload.get("url") or "")
    if not _is_codex_analytics_url(url):
        return False
    if _payload_has_usage_signal(payload):
        return False
    body_text = str(payload.get("body_text") or "").lower()
    return any(marker in body_text for marker in ("codex", "chatgpt", "tasks", "cloud"))


def _is_weekly_only_usage_layout(body_text: str) -> bool:
    """Return whether Codex rendered the newer shared weekly-limit layout."""
    text = re.sub(r"\s+", " ", body_text or "").lower()
    if "weekly usage limit" not in text:
        return False
    return any(
        marker in text
        for marker in (
            "shared agentic usage limit",
            "credits remaining",
            "usage breakdown",
        )
    )


def _is_logged_out_payload(payload: dict[str, Any]) -> bool:
    url = str(payload.get("url") or "").lower()
    if "/auth/login" in url or "/login" in url or "/logout" in url:
        return True
    if bool(payload.get("logged_out")):
        return not (
            has_usage_page_signal(payload) or _looks_like_empty_signed_in_usage(payload)
        )
    return False


def _build_snapshot(
    payload: dict[str, Any],
    *,
    account_id: str = "codex",
) -> UsageSnapshot:
    if _is_logged_out_payload(payload):
        log_page_diagnosis(
            log,
            provider=account_id,
            classification="logged_out",
            payload=payload,
            expected_rows=_EXPECTED_ROWS,
        )
        return UsageSnapshot(
            provider=account_id,
            status=SnapshotStatus.AUTH_REQUIRED,
            error="Not signed in to ChatGPT.",
            raw=payload,
        )
    if is_security_verification_page(payload):
        log_page_diagnosis(
            log,
            provider=account_id,
            classification="security_verification",
            payload=payload,
            expected_rows=_EXPECTED_ROWS,
        )
        return UsageSnapshot(
            provider=account_id,
            status=SnapshotStatus.AUTH_REQUIRED,
            error="ChatGPT security verification required. Click Connect and complete the browser check.",
            raw=payload,
        )

    body_text = str(payload.get("body_text") or "")
    metrics: list[UsageMetric] = []

    def append_metric(key: str, card: dict[str, Any] | None) -> None:
        if not card:
            return
        try:
            source_percent = float(card.get("percent"))
        except (TypeError, ValueError):
            return
        kind = str(card.get("kind") or "").lower()
        if not 0 <= source_percent <= 100 or kind not in ("remaining", "used"):
            return
        if key == "overview_weekly" and not card.get("reset_text"):
            idle_quota = (kind == "remaining" and source_percent == 100) or (
                kind == "used" and source_percent == 0
            ) or re.search(r"starts? when (?:you )?use|開始使用", str(card.get("raw") or ""), re.IGNORECASE)
            if not idle_quota:
                return
        percent = normalize_percent(source_percent, kind)
        resets_at = _parse_reset_text(card.get("reset_text"))
        reset_window = timedelta(hours=5) if key == "session" else timedelta(days=7)
        resets_at, reset_label, idle_note = idle_reset_state(
            percent=percent,
            resets_at=resets_at,
            window=reset_window,
        )
        note = idle_note or card.get("reset_text")
        metrics.append(
            UsageMetric(
                label="Session" if key == "session" else "Weekly",
                percent_used=percent,
                resets_at=resets_at,
                reset_label=reset_label,
                note=note,
                window=reset_window,
            )
        )

    if payload.get("overview_confirmed") is True:
        session_present = bool(re.search(r"5 hour usage limit", body_text, re.IGNORECASE))
        session = payload.get("session")
        if session_present and not session:
            session = _parse_body_card(body_text, "5 hour usage limit", ("Weekly limits", "Weekly usage limit"))
        if session_present and not session:
            log_page_diagnosis(
                log,
                provider=account_id,
                classification="partial_usage_rows",
                payload=payload,
                expected_rows=_EXPECTED_ROWS,
                level=logging.WARNING,
            )
            return UsageSnapshot(
                provider=account_id,
                status=SnapshotStatus.ERROR,
                error="Codex Overview only rendered part of the usage cards; retrying.",
                raw=payload,
            )
        append_metric("session", session)
        card = payload.get("weekly")
        if not card:
            card = _parse_overview_weekly(body_text)
        append_metric("overview_weekly", card)
    else:
        for key, source_label, next_labels in (
            ("session", "5 hour usage limit", ("Weekly usage limit",)),
            ("weekly", "Weekly usage limit", ("Personal usage", "Team usage")),
        ):
            card = payload.get(key) or _parse_body_card(body_text, source_label, next_labels)
            append_metric(key, card)

    labels = {metric.label.lower(): metric for metric in metrics}
    # Accept a lone Weekly card only when the surrounding page identifies the
    # new shared-agentic layout. This preserves transient-error retries for a
    # genuinely partial render of the older Session + Weekly layout.
    weekly_only_layout = payload.get("overview_confirmed") is True and set(labels) == {"weekly"}
    weekly_only_layout = weekly_only_layout or (
        set(labels) == {"weekly"} and _is_weekly_only_usage_layout(body_text)
    )
    if metrics and set(labels) != {"session", "weekly"} and not weekly_only_layout:
        log_page_diagnosis(
            log,
            provider=account_id,
            classification="partial_usage_rows",
            payload=payload,
            expected_rows=_EXPECTED_ROWS,
            level=logging.WARNING,
        )
        return UsageSnapshot(
            provider=account_id,
            status=SnapshotStatus.ERROR,
            error="Codex usage page only rendered part of the usage cards; retrying.",
            raw=payload,
        )

    if not metrics or all(m.percent_used is None for m in metrics):
        if _looks_like_empty_signed_in_usage(payload):
            log_page_diagnosis(
                log,
                provider=account_id,
                classification="empty_signed_in_usage",
                payload=payload,
                expected_rows=_EXPECTED_ROWS,
                level=logging.WARNING,
            )
            return UsageSnapshot(
                provider=account_id,
                status=SnapshotStatus.ERROR,
                error="Codex analytics loaded without usage cards; retrying.",
                raw=payload,
            )
        log_page_diagnosis(
            log,
            provider=account_id,
            classification="layout_changed",
            payload=payload,
            expected_rows=_EXPECTED_ROWS,
            level=logging.WARNING,
        )
        return UsageSnapshot(
            provider=account_id,
            status=SnapshotStatus.ERROR,
            error="Could not read usage from page (layout may have changed).",
            raw=payload,
        )

    return UsageSnapshot(
        provider=account_id,
        status=SnapshotStatus.OK,
        metrics=metrics,
        raw=payload,
    )


class CodexProvider(Provider):
    name = "codex"
    display_name = "Codex"

    def __init__(self, parent: QObject | None = None, account_id: str = "codex"):
        self._parent = parent
        self._account_id = account_id
        self._runner: ScrapeRunner | None = None  # held to prevent GC

    def refresh(self, on_done: Callable[[UsageSnapshot], None]) -> None:
        def _build(payload: dict[str, Any]) -> UsageSnapshot:
            return _build_snapshot(payload, account_id=self._account_id)

        cache_buster = int(datetime.now().timestamp())
        self._runner = ScrapeRunner(
            account_id=self._account_id,
            url=f"{CODEX_USAGE_URL}?aigauge_ts={cache_buster}",
            extractor_js=EXTRACTOR_JS,
            build=_build,
            log=log,
            wait_ms=7000,
            transport_max_attempts=1,
            build_max_attempts=2,
            parent=self._parent,
        )
        self._runner.run(on_done)
