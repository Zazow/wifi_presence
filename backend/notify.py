"""Arrive/leave notifications.

Pure transition detection (testable) + best-effort delivery to ntfy and/or a
generic webhook. Delivery never raises — a failing notifier must not affect
presence tracking.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any


def presence_transitions(
    prev: dict[int, bool], curr: dict[int, bool]
) -> list[dict[str, Any]]:
    """Compare previous and current per-person home flags; return transitions.

    Only people present in BOTH snapshots can transition (so a brand-new person,
    or the first poll after startup, never fires a spurious notification).
    """
    out: list[dict[str, Any]] = []
    for pid, home in curr.items():
        if pid in prev and prev[pid] != home:
            out.append({"person_id": pid, "event": "arrived" if home else "left"})
    return out


def enabled(settings: dict[str, Any]) -> bool:
    return bool(settings.get("notify_ntfy_url") or settings.get("notify_webhook_url"))


def message_for(person_name: str, event: str) -> str:
    return f"{person_name} {'arrived home' if event == 'arrived' else 'left'}"


def _post(url: str, data: bytes, headers: dict[str, str], timeout: float = 6.0) -> None:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    urllib.request.urlopen(req, timeout=timeout).read()


def send(settings: dict[str, Any], person_name: str, event: str) -> None:
    """Best-effort fan-out to configured channels. Swallows all errors."""
    msg = message_for(person_name, event)
    ntfy = (settings.get("notify_ntfy_url") or "").strip()
    webhook = (settings.get("notify_webhook_url") or "").strip()

    if ntfy:
        try:
            _post(
                ntfy,
                data=msg.encode("utf-8"),
                headers={
                    "Title": "WiFi Presence",
                    "Tags": "house" if event == "arrived" else "wave",
                },
            )
        except Exception:
            pass

    if webhook:
        try:
            _post(
                webhook,
                data=json.dumps(
                    {"event": event, "person": person_name, "message": msg}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
        except Exception:
            pass
