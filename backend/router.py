"""ASUS router SSH client + output parsers.

Design notes:
  - One paramiko connection is reused across poll cycles (keepalive enabled) so
    we don't pay TCP+auth setup every 30s. This keeps router load negligible.
  - Parsing is split into pure functions (parse_assoclist / parse_neigh /
    parse_leases / merge_observations) so they can be unit-tested against
    captured command output without a live router.

The "present" set comes from `wl assoclist` (devices currently associated to
wifi). ARP/neighbour and DHCP leases only enrich IP and hostname.
"""
from __future__ import annotations

import re
import threading
from typing import Any, Optional

try:
    import paramiko
except ImportError:  # allow importing parsers without paramiko installed
    paramiko = None  # type: ignore

from .oui import lookup_vendor, normalize_mac

_MAC_RE = re.compile(r"([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})")


def _canon(mac: str) -> str:
    """Canonical lowercase colon-separated MAC for use as a dict/DB key."""
    n = normalize_mac(mac).lower()
    return ":".join(n[i : i + 2] for i in range(0, 12, 2))


# ---- pure parsers --------------------------------------------------------
def parse_assoclist(output: str, iface: str) -> dict[str, str]:
    """`wl assoclist` lines look like: 'assoclist AA:BB:CC:DD:EE:FF'.

    Returns {mac: iface} for every associated client.
    """
    result: dict[str, str] = {}
    for line in output.splitlines():
        m = _MAC_RE.search(line)
        if m:
            result[_canon(m.group(1))] = iface
    return result


def parse_neigh(output: str) -> dict[str, str]:
    """Parse `ip neigh show` OR `/proc/net/arp` into {mac: ip}.

    `ip neigh`:   192.168.1.23 dev br0 lladdr aa:bb:.. REACHABLE
    `/proc/net/arp` header + rows: IP HWtype Flags HWaddress Mask Device
    """
    result: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("ip address"):
            continue
        mac_m = _MAC_RE.search(line)
        if not mac_m:
            continue
        ip_m = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
        if not ip_m:
            continue
        # Skip clearly-stale entries.
        if "FAILED" in line or "INCOMPLETE" in line or "00:00:00:00:00:00" in line:
            continue
        result[_canon(mac_m.group(1))] = ip_m.group(1)
    return result


def parse_leases(output: str) -> dict[str, str]:
    """dnsmasq.leases rows: '<expiry> <mac> <ip> <hostname> <clientid>'.

    Returns {mac: hostname} (hostname '*' treated as unknown).
    """
    result: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        mac, _ip, hostname = parts[1], parts[2], parts[3]
        if not _MAC_RE.search(mac):
            continue
        if hostname and hostname != "*":
            result[_canon(mac)] = hostname
    return result


def merge_observations(
    associated: dict[str, str],
    ip_by_mac: dict[str, str],
    host_by_mac: dict[str, str],
) -> list[dict[str, Any]]:
    """Build the normalized observation list for currently-present devices.

    Only associated (wifi-connected) MACs are reported as present; the other
    maps just enrich them.
    """
    observations = []
    for mac, iface in associated.items():
        observations.append(
            {
                "mac": mac,
                "interface": iface,
                "ip": ip_by_mac.get(mac),
                "hostname": host_by_mac.get(mac),
                "vendor": lookup_vendor(mac),
            }
        )
    return observations


# ---- live SSH client -----------------------------------------------------
class RouterClient:
    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self._client: Optional["paramiko.SSHClient"] = None
        self._lock = threading.Lock()

    def update_settings(self, settings: dict[str, Any]) -> None:
        with self._lock:
            self.settings = settings
            self._close_locked()  # force reconnect with new creds next time

    def _close_locked(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def _ensure_connection(self) -> "paramiko.SSHClient":
        if paramiko is None:
            raise RuntimeError("paramiko is not installed")
        transport = self._client.get_transport() if self._client else None
        if self._client is not None and transport is not None and transport.is_active():
            return self._client
        self._close_locked()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        s = self.settings
        kwargs: dict[str, Any] = {
            "hostname": s["router_host"],
            "port": int(s.get("router_port", 22)),
            "username": s["router_user"],
            "timeout": 10,
            "banner_timeout": 10,
            "auth_timeout": 10,
            "look_for_keys": False,
            "allow_agent": False,
        }
        key_path = s.get("router_key_path")
        if key_path:
            kwargs["key_filename"] = key_path
        else:
            kwargs["password"] = s.get("router_password", "")
        client.connect(**kwargs)
        t = client.get_transport()
        if t is not None:
            t.set_keepalive(30)
        self._client = client
        return client

    def _run(self, client: "paramiko.SSHClient", command: str) -> str:
        _stdin, stdout, _stderr = client.exec_command(command, timeout=15)
        return stdout.read().decode("utf-8", "replace")

    def fetch_clients(self) -> list[dict[str, Any]]:
        """Run the discovery commands and return normalized observations.

        Raises on connection/auth failure so the poller can apply backoff.
        """
        with self._lock:
            client = self._ensure_connection()
            s = self.settings

            ifnames_out = self._run(client, s["cmd_ifnames"])
            ifaces = ifnames_out.split()

            associated: dict[str, str] = {}
            for iface in ifaces:
                cmd = s["cmd_assoclist"].format(iface=iface)
                associated.update(parse_assoclist(self._run(client, cmd), iface))

            ip_by_mac = parse_neigh(self._run(client, s["cmd_neigh"]))
            host_by_mac = parse_leases(self._run(client, s["cmd_leases"]))

        return merge_observations(associated, ip_by_mac, host_by_mac)

    def test_connection(self) -> dict[str, Any]:
        """Used by the Settings 'Test connection' button."""
        try:
            with self._lock:
                client = self._ensure_connection()
                ifnames_out = self._run(client, self.settings["cmd_ifnames"])
            ifaces = ifnames_out.split()
            return {"ok": True, "interfaces": ifaces}
        except Exception as e:  # surface a readable error to the UI
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
