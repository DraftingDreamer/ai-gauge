from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from ._resets_common import ResetEvent, ResetWatch, ResetsFetchError, ResetsProviderBase


CODEX_RESETS_URL = "https://codex-resets.com/api/v1/status"


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_watch(value: object) -> ResetWatch | None:
    if not isinstance(value, dict):
        return None
    try:
        level = value["level"]
        chance = value["reset_chance_percent"]
        forecast = value["forecast_window"]
        observed = value["observed_at"]
        expires = value["expires_at"]
        text = value["text"]
        source = value["source"]
        if level not in ("elevated", "strong"):
            return None
        if chance is not None and (type(chance) is not int or not 0 <= chance <= 100):
            return None
        if not all(isinstance(item, str) for item in (forecast, observed, expires, text)):
            return None
        if not isinstance(source, dict):
            return None
        source_type = source["type"]
        if source_type == "x_post":
            if source.get("author") != "thsottiaux":
                return None
            url = source["url"]
        elif source_type == "observed":
            url = source.get("url")
        else:
            return None
        if url is not None and (
            not isinstance(url, str)
            or urlparse(url).scheme not in ("http", "https")
            or not urlparse(url).netloc
        ):
            return None
        if source_type == "x_post" and url is None:
            return None
        observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        expires_at = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        if observed_at.utcoffset() is None or expires_at.utcoffset() is None:
            return None
        return ResetWatch(
            level, chance, forecast,
            observed_at.astimezone(timezone.utc),
            expires_at.astimezone(timezone.utc), text, url,
        )
    except (KeyError, TypeError, ValueError):
        return None


class CodexResetsProvider(ResetsProviderBase):
    name = "codex_resets"
    display_name = "Codex Resets"
    URL = CODEX_RESETS_URL
    use_etag = True

    def _fetch_latest_event(self) -> ResetEvent | None:
        payload = self._get_json(self.URL, use_etag=self.use_etag)
        if payload is None:
            return self.latest_event
        data = payload["data"]
        candidates: list[tuple[ResetEvent, bool]] = []

        scheduled = data.get("scheduled_reset")
        if scheduled is not None:
            reset_type = scheduled["reset_type"]
            candidates.append(
                (
                    ResetEvent(
                        kind="announced",
                        id=str(scheduled["id"]),
                        at=_parse_time(scheduled["announced_at"]),
                        summary=f"{reset_type} reset",
                        detail=scheduled.get("text") or "",
                        url=(scheduled.get("source") or {}).get("url"),
                    ),
                    True,
                )
            )

        latest = data.get("latest_reset")
        if latest is not None:
            reset_type = latest["reset_type"]
            if reset_type == "regular":
                kind, summary = "landed", "limits refilled"
            elif reset_type == "banked":
                kind, summary = "banked", "reset credit granted"
            else:
                raise ResetsFetchError("unexpected reset type")
            candidates.append(
                (
                    ResetEvent(
                        kind=kind,
                        id=str(latest["id"]),
                        at=_parse_time(latest["announced_at"]),
                        summary=summary,
                        detail=latest.get("text") or "",
                        url=(latest.get("source") or {}).get("url"),
                    ),
                    False,
                )
            )

        event = max(candidates, key=lambda item: (item[0].at, item[1]))[0] if candidates else None
        self.latest_watch = _parse_watch(data.get("active_watch"))
        return event
