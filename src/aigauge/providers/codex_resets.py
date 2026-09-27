from __future__ import annotations

from datetime import datetime, timezone

from ._resets_common import ResetEvent, ResetsFetchError, ResetsProviderBase


CODEX_RESETS_URL = "https://codex-resets.com/api/v1/status"


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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

        if not candidates:
            return None
        return max(candidates, key=lambda item: (item[0].at, item[1]))[0]
