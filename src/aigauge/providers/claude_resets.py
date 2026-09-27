from __future__ import annotations

from datetime import datetime, timezone

from ._resets_common import ResetEvent, ResetsFetchError, ResetsProviderBase


CLAUDE_RESETS_URL = "https://claude-resets.com/api/resets"


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class ClaudeResetsProvider(ResetsProviderBase):
    name = "claude_resets"
    display_name = "Claude Resets"
    URL = CLAUDE_RESETS_URL
    use_etag = False

    def _fetch_latest_event(self) -> ResetEvent | None:
        payload = self._get_json(self.URL, use_etag=self.use_etag)
        if payload is None:
            return self.latest_event
        try:
            events = payload["providers"]["claude"]["events"]
        except (KeyError, TypeError) as exc:
            raise ResetsFetchError("unexpected payload") from exc
        if not isinstance(events, list):
            raise ResetsFetchError("unexpected payload")

        resets = [event for event in events if event["kind"] == "reset"]
        if not resets:
            return None
        event = max(resets, key=lambda item: _parse_time(item["date"]))
        reset_type = event.get("resetType")
        scope = event.get("scope")
        if reset_type == "banked":
            kind, summary = "banked", "reset credit"
        else:
            kind, summary = "landed", "limits refilled"
        if scope:
            summary += f" ({scope})"

        provisional = event.get("verification") == "provisional"
        detail = event.get("note") or ""
        if provisional:
            detail = f"Unconfirmed (provisional). {detail}"
        return ResetEvent(
            kind=kind,
            id=str(event["id"]),
            at=_parse_time(event["date"]),
            summary=summary,
            detail=detail,
            url=event.get("url"),
            provisional=provisional,
        )
