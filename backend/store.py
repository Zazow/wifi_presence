"""SQLite persistence layer: people, devices, mappings, settings.

Single source of truth. All settings and device->person mappings survive
restarts because they live in this database file.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

DEFAULT_SETTINGS: dict[str, Any] = {
    "router_host": "192.168.1.1",
    "router_port": 22,
    "router_user": "admin",
    "router_password": "",
    "router_key_path": "",  # optional private key; takes priority over password
    "poll_interval": 30,  # seconds
    "grace_minutes": 10,
    # Advanced command overrides. Empty string => use built-in default.
    "cmd_ifnames": "nvram get wl_ifnames",
    "cmd_assoclist": "wl -i {iface} assoclist",
    "cmd_neigh": "ip neigh show",
    "cmd_leases": "cat /var/lib/misc/dnsmasq.leases 2>/dev/null",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    mac TEXT PRIMARY KEY,
    hostname TEXT,
    ip TEXT,
    vendor TEXT,
    interface TEXT,
    label TEXT,
    person_id INTEGER REFERENCES people(id) ON DELETE SET NULL,
    ignored INTEGER NOT NULL DEFAULT 0,
    first_seen REAL,
    last_seen REAL,
    is_present INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _now() -> float:
    return time.time()


class Store:
    def __init__(self, path: str | Path = "wifi_presence.db"):
        self.path = str(path)
        # check_same_thread=False because the async poller and the request
        # handlers may touch the connection from different threads; we guard
        # with a lock.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            for key, value in DEFAULT_SETTINGS.items():
                self._conn.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                    (key, json.dumps(value)),
                )
            self._conn.commit()

    # ---- settings ---------------------------------------------------------
    def get_settings(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        result = dict(DEFAULT_SETTINGS)
        for row in rows:
            result[row["key"]] = json.loads(row["value"])
        return result

    def update_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            for key, value in updates.items():
                self._conn.execute(
                    "INSERT INTO settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)),
                )
            self._conn.commit()
        return self.get_settings()

    # ---- people -----------------------------------------------------------
    def list_people(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM people ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [dict(r) for r in rows]

    def create_person(self, name: str) -> dict[str, Any]:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO people(name, created_at) VALUES (?, ?)",
                (name, _now()),
            )
            self._conn.commit()
            pid = cur.lastrowid
            row = self._conn.execute(
                "SELECT * FROM people WHERE id = ?", (pid,)
            ).fetchone()
        return dict(row)

    def rename_person(self, person_id: int, name: str) -> Optional[dict[str, Any]]:
        with self._lock:
            self._conn.execute(
                "UPDATE people SET name = ? WHERE id = ?", (name, person_id)
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM people WHERE id = ?", (person_id,)
            ).fetchone()
        return dict(row) if row else None

    def delete_person(self, person_id: int) -> None:
        with self._lock:
            # ON DELETE SET NULL unassigns the devices.
            self._conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
            self._conn.commit()

    # ---- devices ----------------------------------------------------------
    def list_devices(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM devices").fetchall()
        return [dict(r) for r in rows]

    def update_device(self, mac: str, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
        allowed = {"label", "person_id", "ignored"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return self.get_device(mac)
        if "ignored" in sets:
            sets["ignored"] = 1 if sets["ignored"] else 0
        assignments = ", ".join(f"{k} = ?" for k in sets)
        params = list(sets.values()) + [mac]
        with self._lock:
            self._conn.execute(
                f"UPDATE devices SET {assignments} WHERE mac = ?", params
            )
            self._conn.commit()
        return self.get_device(mac)

    def get_device(self, mac: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM devices WHERE mac = ?", (mac,)
            ).fetchone()
        return dict(row) if row else None

    def record_observations(
        self, observations: list[dict[str, Any]], seen_at: float
    ) -> None:
        """Upsert observed devices and refresh presence flags.

        `observations` is a list of {mac, ip, hostname, interface, vendor}.
        Devices not in this batch get is_present = 0 (their last_seen is
        preserved so the presence engine can apply the grace window).
        """
        seen_macs = {o["mac"] for o in observations}
        with self._lock:
            for o in observations:
                mac = o["mac"]
                existing = self._conn.execute(
                    "SELECT mac, first_seen FROM devices WHERE mac = ?", (mac,)
                ).fetchone()
                if existing is None:
                    self._conn.execute(
                        "INSERT INTO devices(mac, hostname, ip, vendor, interface, "
                        "first_seen, last_seen, is_present) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                        (
                            mac,
                            o.get("hostname"),
                            o.get("ip"),
                            o.get("vendor"),
                            o.get("interface"),
                            seen_at,
                            seen_at,
                        ),
                    )
                else:
                    # Only overwrite enrichment fields when we have a value, so
                    # a momentarily missing hostname/ip doesn't wipe a good one.
                    self._conn.execute(
                        "UPDATE devices SET "
                        "hostname = COALESCE(?, hostname), "
                        "ip = COALESCE(?, ip), "
                        "vendor = COALESCE(?, vendor), "
                        "interface = COALESCE(?, interface), "
                        "last_seen = ?, is_present = 1 "
                        "WHERE mac = ?",
                        (
                            o.get("hostname"),
                            o.get("ip"),
                            o.get("vendor"),
                            o.get("interface"),
                            seen_at,
                            mac,
                        ),
                    )
            # Mark everything else as not currently present.
            if seen_macs:
                placeholders = ",".join("?" for _ in seen_macs)
                self._conn.execute(
                    f"UPDATE devices SET is_present = 0 "
                    f"WHERE mac NOT IN ({placeholders})",
                    tuple(seen_macs),
                )
            else:
                self._conn.execute("UPDATE devices SET is_present = 0")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
