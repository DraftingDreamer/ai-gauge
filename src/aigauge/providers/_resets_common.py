from __future__ import annotations

from dataclasses import dataclass
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Callable

import requests

from .. import __version__
from ..models import SnapshotStatus, UsageMetric, UsageSnapshot
from .base import Provider


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

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.id}"


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
) -> UsageSnapshot:
    dismissed = event is not None and event.key == dismissed_key
    metrics: list[UsageMetric] = []
    if event is not None and not dismissed:
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
    return UsageSnapshot(
        provider=provider,
        status=SnapshotStatus.ERROR if error is not None else SnapshotStatus.OK,
        metrics=metrics,
        fetched_at=now.astimezone().replace(tzinfo=None),
        error=error,
        raw={
            "event_key": event.key if event is not None else None,
            "event_kind": event.kind if event is not None else None,
            "event_url": event.url if event is not None else None,
            "provisional": event.provisional if event is not None else False,
            "dismissed": dismissed,
        },
    )


class ResetsProviderBase(Provider):
    MIN_INTERVAL = timedelta(minutes=15)
    TIMEOUT_S = 15

    def __init__(self, clock: Callable[[], datetime] | None = None):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.dismissed_event_key: str | None = None
        self.latest_event: ResetEvent | None = None
        self._etag: str | None = None
        self._last_success_at: datetime | None = None
        self._next_allowed_at = datetime.min.replace(tzinfo=timezone.utc)

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
            raise ResetsFetchError(
                f"network error: {type(exc).__name__}"
            ) from exc

        if response.status_code == 304:
            return None
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            try:
                seconds = float(retry_after) if retry_after is not None else None
            except ValueError:
                seconds = None
            if seconds is None or seconds < 0:
                seconds = self.MIN_INTERVAL.total_seconds()
            self._next_allowed_at = self._clock() + timedelta(seconds=seconds)
            raise ResetsFetchError("rate limited")
        if not 200 <= response.status_code < 300:
            raise ResetsFetchError(f"HTTP {response.status_code}")
        if response.status_code != 200:
            raise ResetsFetchError(f"HTTP {response.status_code}")

        if use_etag and response.headers.get("ETag"):
            self._etag = response.headers["ETag"]
        try:
            payload = response.json()
        except ValueError as exc:
            raise ResetsFetchError("invalid JSON") from exc
        if not isinstance(payload, dict):
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
                    self.name, self.latest_event, self.dismissed_event_key, now
                )
            try:
                event = self._fetch_latest_event()
            except (ResetsFetchError, KeyError, TypeError, ValueError) as exc:
                return build_snapshot(
                    self.name,
                    self.latest_event,
                    self.dismissed_event_key,
                    now,
                    error=str(exc)[:200],
                )
            self.latest_event = event
            self._last_success_at = now
            return build_snapshot(
                self.name, self.latest_event, self.dismissed_event_key, now
            )

        self._run_async(work, on_done)
