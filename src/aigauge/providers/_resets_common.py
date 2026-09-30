from __future__ import annotations

from dataclasses import dataclass
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import math
from urllib.parse import urlsplit
from typing import Callable

import requests

from .. import __version__
from ..models import SnapshotStatus, UsageMetric, UsageSnapshot
from .base import Provider


RESET_ANNOUNCEMENT_PROVIDERS = frozenset({"codex_resets", "claude_resets"})


@dataclass
class _ResetsState:
    latest_event: ResetEvent | None = None
    latest_watch: ResetWatch | None = None
    etag: str | None = None
    last_success_at: datetime | None = None
    next_allowed_at: datetime = datetime.min.replace(tzinfo=timezone.utc)
    last_error: str | None = None


_PROCESS_STATES: dict[str, _ResetsState] = {}


def _valid_http_url(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    return value if parsed.scheme.lower() in {"http", "https"} and parsed.netloc else None


@dataclass(frozen=True)
class ResetEvent:
    kind: str
    id: str
    at: datetime
    summary: str
    detail: str
    url: str | None
    provisional: bool = False

    def __post_init__(self) -> None:
        if self.kind not in {"announced", "landed", "banked"}:
            raise ValueError(f"invalid reset event kind: {self.kind}")
        if self.at.tzinfo is None or self.at.utcoffset() is None:
            raise ValueError("event time must be timezone-aware")
        object.__setattr__(self, "at", self.at.astimezone(timezone.utc))
        object.__setattr__(self, "url", _valid_http_url(self.url))

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.id}"


@dataclass(frozen=True)
class ResetWatch:
    level: str
    reset_chance_percent: int | None
    forecast_window: str
    observed_at: datetime
    expires_at: datetime
    text: str
    source_url: str | None

    @property
    def key(self) -> str:
        return f"{self.observed_at.astimezone(timezone.utc).isoformat()}:{self.level}"


def watch_is_dismissed(watch: ResetWatch, dismissed_key: str | None) -> bool:
    observed = watch.observed_at.astimezone(timezone.utc).isoformat()
    return dismissed_key == f"{observed}:{watch.level}" or (
        watch.level == "elevated" and dismissed_key == f"{observed}:strong"
    )


KIND_LABEL = {"announced": "Announced", "landed": "Reset", "banked": "Banked"}


class ResetsFetchError(Exception):
    """A safe, user-facing error while retrieving reset announcements."""


def relative_age(then: datetime, now: datetime) -> str:
    seconds = max(0, int((now - then).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def build_snapshot(
    provider: str,
    event: ResetEvent | None,
    dismissed_key: str | None,
    now: datetime,
    error: str | None = None,
    watch: ResetWatch | None = None,
    dismissed_watch_key: str | None = None,
) -> UsageSnapshot:
    event_dismissed = event is not None and event.key == dismissed_key
    active_watch = watch if watch is not None and now < watch.expires_at else None
    watch_dismissed = (
        active_watch is not None
        and watch_is_dismissed(active_watch, dismissed_watch_key)
    )
    dismissed = (event is not None or active_watch is not None) and (
        event is None or event_dismissed
    ) and (active_watch is None or watch_dismissed)
    metrics: list[UsageMetric] = []
    if event is not None and not event_dismissed:
        metrics.append(
            UsageMetric(
                label=(
                    f"{KIND_LABEL[event.kind]} · {event.summary}, "
                    f"{relative_age(event.at, now)}"
                ),
                percent_used=None,
                resets_at=None,
                reset_label=None,
                window=None,
                note=event.detail,
                tag=None,
            )
        )
    if active_watch is not None and not watch_dismissed:
        chance = active_watch.reset_chance_percent
        value = active_watch.level
        if chance is not None:
            value += f" · {chance}%"
        value += f" · {active_watch.forecast_window} (AI)"
        metrics.append(
            UsageMetric(
                label=f"Watch · {value}",
                percent_used=None,
                resets_at=None,
                reset_label=None,
                window=None,
                note=(
                    f"{active_watch.text}\n{active_watch.forecast_window}\n"
                    "AI forecast by Codex Resets, not an official announcement."
                ),
                tag=None,
            )
        )
    return UsageSnapshot(
        provider=provider,
        status=SnapshotStatus.ERROR if error is not None else SnapshotStatus.OK,
        metrics=metrics,
        fetched_at=now.astimezone().replace(tzinfo=None),
        error=error,
        raw={
            "event_key": event.key if event is not None else None,
            "event_at": (
                event.at.astimezone(timezone.utc).isoformat()
                if event is not None else None
            ),
            "event_kind": event.kind if event is not None else None,
            "event_summary": event.summary if event is not None else None,
            "event_detail": event.detail if event is not None else None,
            "event_url": event.url if event is not None else None,
            "event_has_url": bool(event is not None and event.url),
            "provisional": event.provisional if event is not None else False,
            "event_dismissed": event_dismissed,
            "dismissed": dismissed,
            "watch_key": active_watch.key if active_watch is not None else None,
            "watch_level": active_watch.level if active_watch is not None else None,
            "watch_chance": (
                active_watch.reset_chance_percent if active_watch is not None else None
            ),
            "watch_forecast_window": (
                active_watch.forecast_window if active_watch is not None else None
            ),
            "watch_text": active_watch.text if active_watch is not None else None,
            "watch_observed_at": (
                active_watch.observed_at.astimezone(timezone.utc).isoformat()
                if active_watch is not None else None
            ),
            "watch_expires_at": (
                active_watch.expires_at.astimezone(timezone.utc).isoformat()
                if active_watch is not None else None
            ),
            "watch_url": active_watch.source_url if active_watch is not None else None,
            "watch_has_url": bool(active_watch is not None and active_watch.source_url),
            "watch_dismissed": watch_dismissed,
        },
    )


class ResetsProviderBase(Provider):
    MIN_INTERVAL = timedelta(minutes=15)
    TIMEOUT_S = 15

    def __init__(self, clock: Callable[[], datetime] | None = None):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.dismissed_event_key: str | None = None
        self.dismissed_watch_key: str | None = None
        self._state = _PROCESS_STATES.setdefault(self.name, _ResetsState())
        self._pending_etag: str | None = None
        self._pending_retry_after: str | None = None

    @property
    def latest_event(self) -> ResetEvent | None:
        return self._state.latest_event

    @latest_event.setter
    def latest_event(self, value: ResetEvent | None) -> None:
        self._state.latest_event = value

    @property
    def latest_watch(self) -> ResetWatch | None:
        return self._state.latest_watch

    @latest_watch.setter
    def latest_watch(self, value: ResetWatch | None) -> None:
        self._state.latest_watch = value

    @property
    def _etag(self) -> str | None:
        return self._state.etag

    @_etag.setter
    def _etag(self, value: str | None) -> None:
        self._state.etag = value

    @property
    def _last_success_at(self) -> datetime | None:
        return self._state.last_success_at

    @_last_success_at.setter
    def _last_success_at(self, value: datetime | None) -> None:
        self._state.last_success_at = value

    @property
    def _next_allowed_at(self) -> datetime:
        return self._state.next_allowed_at

    @_next_allowed_at.setter
    def _next_allowed_at(self, value: datetime) -> None:
        self._state.next_allowed_at = value

    @property
    def _last_error(self) -> str | None:
        return self._state.last_error

    @_last_error.setter
    def _last_error(self, value: str | None) -> None:
        self._state.last_error = value

    def _defer_after_failure(self, retry_after: str | None = None) -> None:
        try:
            seconds = float(retry_after) if retry_after is not None else 0
        except (TypeError, ValueError):
            try:
                retry_at = parsedate_to_datetime(retry_after) if retry_after else None
                if retry_at is not None:
                    if retry_at.tzinfo is None or retry_at.utcoffset() is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    seconds = (retry_at.astimezone(timezone.utc) - self._clock()).total_seconds()
                else:
                    seconds = 0
            except (TypeError, ValueError, OverflowError):
                seconds = 0
        if not math.isfinite(seconds):
            seconds = 0
        seconds = max(0, seconds)
        delay = max(self.MIN_INTERVAL.total_seconds(), seconds)
        self._next_allowed_at = self._clock() + timedelta(seconds=delay)

    def _get_json(self, url: str, use_etag: bool) -> dict | None:
        headers = {
            "User-Agent": (
                f"ai-gauge/{__version__} "
                "(+https://github.com/DraftingDreamer/ai-gauge)"
            )
        }
        if use_etag and self._etag:
            headers["If-None-Match"] = self._etag
        try:
            response = requests.get(url, headers=headers, timeout=self.TIMEOUT_S)
        except requests.RequestException as exc:
            self._defer_after_failure()
            raise ResetsFetchError(
                f"network error: {type(exc).__name__}"
            ) from exc

        self._pending_retry_after = response.headers.get("Retry-After")
        if response.status_code == 304:
            return None
        if response.status_code == 429:
            self._defer_after_failure(self._pending_retry_after)
            raise ResetsFetchError("rate limited")
        if not 200 <= response.status_code < 300:
            self._defer_after_failure(self._pending_retry_after)
            raise ResetsFetchError(f"HTTP {response.status_code}")
        if response.status_code != 200:
            self._defer_after_failure(self._pending_retry_after)
            raise ResetsFetchError(f"HTTP {response.status_code}")

        if use_etag and response.headers.get("ETag"):
            self._pending_etag = response.headers["ETag"]
        try:
            payload = response.json()
        except ValueError as exc:
            self._defer_after_failure(self._pending_retry_after)
            raise ResetsFetchError("invalid JSON") from exc
        if not isinstance(payload, dict):
            self._defer_after_failure(self._pending_retry_after)
            raise ResetsFetchError("unexpected payload")
        return payload

    @abstractmethod
    def _fetch_latest_event(self) -> ResetEvent | None:
        raise NotImplementedError

    def refresh(self, on_done: Callable[[UsageSnapshot], None]) -> None:
        def work() -> UsageSnapshot:
            now = self._clock()
            if now < self._next_allowed_at or (
                self._last_success_at is not None
                and now - self._last_success_at < self.MIN_INTERVAL
            ):
                return build_snapshot(
                    self.name, self.latest_event, self.dismissed_event_key, now,
                    error=self._last_error,
                    watch=self.latest_watch,
                    dismissed_watch_key=self.dismissed_watch_key,
                )
            self._pending_etag = None
            self._pending_retry_after = None
            try:
                event = self._fetch_latest_event()
            except Exception as exc:  # noqa: BLE001
                self._defer_after_failure(self._pending_retry_after)
                self._last_error = str(exc)[:200]
                return build_snapshot(
                    self.name,
                    self.latest_event,
                    self.dismissed_event_key,
                    now,
                    error=self._last_error,
                    watch=self.latest_watch,
                    dismissed_watch_key=self.dismissed_watch_key,
                )
            if self._pending_etag is not None:
                self._etag = self._pending_etag
            self.latest_event = event
            self._last_success_at = now
            self._last_error = None
            return build_snapshot(
                self.name, self.latest_event, self.dismissed_event_key, now,
                watch=self.latest_watch,
                dismissed_watch_key=self.dismissed_watch_key,
            )

        self._run_async(work, on_done)
