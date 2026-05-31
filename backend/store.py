"""SQLite persistence layer: people, devices, mappings, settings.

Single source of truth. All settings and device->person mappings survive
restarts because they live in this database file.
"""
from __future__ import annotations

import ipaddress
import json
import os
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
    # Bridge forwarding table — finds devices behind APs / AiMesh nodes.
    # Empty string disables it (wifi-only via assoclist).
    "cmd_fdb": "brctl showmacs br0 2>/dev/null",
    # Friendly name for the main router (shown as the AP for its own clients).
    "router_name": "Main router",
    # Extra access points to poll for client attribution. Each entry:
    #   {"name", "host", "port", "user", "password", "key_path"}
    # Empty fields fall back to the main router's credentials.
    "access_points": [],
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
    ap TEXT,
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


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# The production database lives in a per-user application data directory,
# OUTSIDE the project working tree. This is deliberate and important:
#   - A relative path would resolve against the current working directory, so
#     launching from a different folder would open a different (empty) DB.
#   - Keeping it inside the repo (e.g. ./data) means routine development and
#     verification activity — `rm` cleanups, `git clean -fdx`, deleting the repo
#     — silently destroys the user's real settings and device mappings.
# So we default to ~/.local/share/wifi-presence/ (or $XDG_DATA_HOME), which
# nothing in the dev/test/cleanup workflow ever touches.
def _default_data_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / "wifi-presence"


DEFAULT_DB_PATH = _default_data_dir() / "wifi_presence.db"


def resolve_db_path(override: str | None = None) -> Path:
    """Resolve the database path to a stable absolute location.

    `override` (e.g. from the WIFI_PRESENCE_DB env var) wins when set; otherwise
    we use the per-user application data directory (outside the repo).
    """
    if override:
        return Path(override).expanduser().resolve()
    return DEFAULT_DB_PATH


def normalize_ip(ip: str) -> str:
    """Canonicalize a client IP for matching.

    Dual-stack sockets often report IPv4 clients as IPv4-mapped IPv6
    (e.g. '::ffff:192.168.1.5'); collapse those to plain IPv4 so they match the
    IPv4 addresses we learn from ARP/DHCP leases.
    """
    if not ip:
        return ip
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return str(addr.ipv4_mapped)
    return str(addr)


def match_device_by_ip(devices: list[dict[str, Any]], ip: str) -> Optional[dict[str, Any]]:
    """Find the device whose last-known IP matches `ip`. Used to identify the
    device a web request came from ('register this device')."""
    ip = normalize_ip(ip)
    if not ip:
        return None
    for d in devices:
        if d.get("ip") == ip:
            return d
    return None


def _now() -> float:
    return time.time()


class Store:
    def __init__(self, path: str | Path = DEFAULT_DB_PATH):
        self.path = str(path)
        db_path = Path(self.path)
        # Whether the DB file existed BEFORE we open it. A brand-new file means
        # we may be able to auto-restore the user's config from a backup.
        existed = db_path.exists()
        # A human-readable config backup lives beside the DB so settings and
        # device mappings can be recovered even if the DB file is ever lost.
        self._backup_path = db_path.parent / "wifi-presence-config-backup.json"
        self._restoring = False
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False because the async poller and the request
        # handlers may touch the connection from different threads; we guard
        # with a lock.
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        self._init_schema()
        if not existed:
            self._restore_from_backup_if_present()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._migrate()
            for key, value in DEFAULT_SETTINGS.items():
                self._conn.execute(
                    "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                    (key, json.dumps(value)),
                )
            self._conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after the first release, without touching
        existing rows (so upgrades never wipe saved data)."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(devices)")}
        if "ap" not in cols:
            self._conn.execute("ALTER TABLE devices ADD COLUMN ap TEXT")

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
        self._write_backup()
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
        self._write_backup()
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
        self._write_backup()
        return dict(row) if row else None

    def delete_person(self, person_id: int) -> None:
        with self._lock:
            # ON DELETE SET NULL unassigns the devices.
            self._conn.execute("DELETE FROM people WHERE id = ?", (person_id,))
            self._conn.commit()
        self._write_backup()

    # ---- devices ----------------------------------------------------------
    def list_devices(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM devices").fetchall()
        return [dict(r) for r in rows]

    def known_wifi_macs(self) -> set[str]:
        """MACs we've ever seen associate to a polled radio (interface is set).
        For these, the assoclist is authoritative — a stale bridge-table entry
        must not keep them 'present'."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT mac FROM devices WHERE interface IS NOT NULL"
            ).fetchall()
        return {r["mac"] for r in rows}

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
        self._write_backup()
        return self.get_device(mac)

    # ---- config backup / restore -----------------------------------------
    def _export_config(self) -> dict[str, Any]:
        """Serialize the precious, hard-to-recreate config: settings, people,
        and device mappings (assignment / label / ignore). Transient presence
        data is intentionally excluded."""
        people = [{"id": p["id"], "name": p["name"]} for p in self.list_people()]
        id_to_name = {p["id"]: p["name"] for p in people}
        device_map = []
        for d in self.list_devices():
            if d.get("person_id") is not None or d.get("label") or d.get("ignored"):
                device_map.append(
                    {
                        "mac": d["mac"],
                        "label": d.get("label"),
                        "ignored": bool(d.get("ignored")),
                        "person_name": id_to_name.get(d.get("person_id")),
                    }
                )
        return {
            "settings": self.get_settings(),
            "people": people,
            "device_map": device_map,
        }

    def _write_backup(self) -> None:
        """Best-effort atomic write of the config backup beside the DB. Never
        raises — a backup failure must not break a real write. Suppressed while
        restoring so we don't clobber the file we're reading from."""
        if self._restoring:
            return
        try:
            data = json.dumps(self._export_config(), indent=2)
            self._backup_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._backup_path.with_suffix(".json.tmp")
            tmp.write_text(data)
            tmp.replace(self._backup_path)  # atomic on POSIX
        except Exception:
            pass

    def _restore_from_backup_if_present(self) -> None:
        """On a brand-new DB, repopulate config from the backup if one exists."""
        if not self._backup_path.exists():
            return
        try:
            data = json.loads(self._backup_path.read_text())
        except Exception:
            return
        self.import_config(data)

    def import_config(self, data: dict[str, Any]) -> None:
        self._restoring = True
        try:
            settings = data.get("settings") or {}
            known = {k: settings[k] for k in settings if k in DEFAULT_SETTINGS}
            if known:
                self.update_settings(known)
            name_to_id: dict[str, int] = {}
            for p in data.get("people") or []:
                name_to_id[p["name"]] = self.create_person(p["name"])["id"]
            for m in data.get("device_map") or []:
                mac = m.get("mac")
                if not mac:
                    continue
                with self._lock:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO devices(mac, is_present) VALUES (?, 0)",
                        (mac,),
                    )
                    self._conn.commit()
                fields: dict[str, Any] = {}
                if m.get("label") is not None:
                    fields["label"] = m["label"]
                if m.get("ignored"):
                    fields["ignored"] = True
                pid = name_to_id.get(m.get("person_name"))
                if pid is not None:
                    fields["person_id"] = pid
                if fields:
                    self.update_device(mac, fields)
        finally:
            self._restoring = False

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
                        "INSERT INTO devices(mac, hostname, ip, vendor, interface, ap, "
                        "first_seen, last_seen, is_present) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                        (
                            mac,
                            o.get("hostname"),
                            o.get("ip"),
                            o.get("vendor"),
                            o.get("interface"),
                            o.get("ap"),
                            seen_at,
                            seen_at,
                        ),
                    )
                else:
                    # Only overwrite enrichment fields when we have a value, so
                    # a momentarily missing hostname/ip/ap doesn't wipe a good one.
                    # (ap stays last-known when this cycle only saw the device via
                    # the bridge table and couldn't attribute it to an AP.)
                    self._conn.execute(
                        "UPDATE devices SET "
                        "hostname = COALESCE(?, hostname), "
                        "ip = COALESCE(?, ip), "
                        "vendor = COALESCE(?, vendor), "
                        "interface = COALESCE(?, interface), "
                        "ap = COALESCE(?, ap), "
                        "last_seen = ?, is_present = 1 "
                        "WHERE mac = ?",
                        (
                            o.get("hostname"),
                            o.get("ip"),
                            o.get("vendor"),
                            o.get("interface"),
                            o.get("ap"),
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
