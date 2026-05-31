"""Presence engine — pure functions, no I/O.

A device counts as "still here" if it was seen within the grace window. A person
is HOME if ANY of their assigned devices is still here. This is what makes the
system tolerant of:
  - someone owning multiple phones (any one present => home), and
  - a phone briefly dropping wifi for 5G (gap < grace window => stays home).
"""
from __future__ import annotations

from typing import Any


def device_active(device: dict[str, Any], now: float, grace_seconds: float) -> bool:
    last_seen = device.get("last_seen")
    if last_seen is None:
        return False
    return (now - last_seen) <= grace_seconds


def compute_state(
    people: list[dict[str, Any]],
    devices: list[dict[str, Any]],
    grace_seconds: float,
    now: float,
) -> dict[str, Any]:
    """Return the full presence state object served to the UI / WebSocket.

    Shape:
    {
      "now": <epoch>,
      "grace_seconds": <n>,
      "people": [
        {"id", "name", "home": bool, "last_seen": float|None,
         "devices": [ {device fields..., "active": bool} ]}
      ],
      "unassigned_present": [ {device fields..., "active": True} ]
    }
    Ignored devices are excluded entirely. `grace_seconds` is the effective
    window (already floored to the poll interval by the caller).
    """
    visible = [d for d in devices if not d.get("ignored")]

    by_person: dict[int, list[dict[str, Any]]] = {}
    for d in visible:
        pid = d.get("person_id")
        if pid is not None:
            by_person.setdefault(pid, []).append(d)

    people_out = []
    for person in people:
        owned = by_person.get(person["id"], [])
        enriched = []
        last_seen_vals = []
        home = False
        for d in owned:
            active = device_active(d, now, grace_seconds)
            home = home or active
            if d.get("last_seen") is not None:
                last_seen_vals.append(d["last_seen"])
            enriched.append({**d, "active": active})
        people_out.append(
            {
                "id": person["id"],
                "name": person["name"],
                "home": home,
                "last_seen": max(last_seen_vals) if last_seen_vals else None,
                "devices": enriched,
            }
        )

    # Present-but-unassigned: actively-seen devices with no person, not ignored.
    unassigned = [
        {**d, "active": True}
        for d in visible
        if d.get("person_id") is None and device_active(d, now, grace_seconds)
    ]

    return {
        "now": now,
        "grace_seconds": grace_seconds,
        "people": people_out,
        "unassigned_present": unassigned,
    }
