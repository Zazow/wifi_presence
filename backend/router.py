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
import socket
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


def parse_fdb(output: str) -> set[str]:
    """Parse the bridge forwarding table into the set of non-local MACs.

    This is what lets us see devices behind APs / AiMesh nodes / wired switches:
    the main router's `wl assoclist` only knows its own wifi clients, but the
    bridge learns every MAC whose traffic crosses it, including clients on other
    access points (forwarded via the AP's uplink port).

    Supports `brctl showmacs <br>` output:
        port no   mac addr            is local?   ageing timer
          1       aa:bb:cc:dd:ee:ff   no             1.23
    and falls back to iproute2 `bridge fdb show`:
        aa:bb:cc:dd:ee:ff dev eth6 master br0
    Local/permanent/self entries (the bridge's own ports) are excluded.
    """
    macs: set[str] = set()
    for line in output.splitlines():
        low = line.lower()
        parts = line.split()
        # brctl showmacs: second column is the MAC, third is is_local?
        if len(parts) >= 3 and _MAC_RE.fullmatch(parts[1] or ""):
            if parts[2].lower() in ("no", "0", "false"):
                mac = _canon(parts[1])
                if mac != "ff:ff:ff:ff:ff:ff":
                    macs.add(mac)
            continue
        # bridge fdb show fallback
        m = _MAC_RE.search(line)
        if m and not any(t in low for t in ("self", "permanent", "local")):
            mac = _canon(m.group(1))
            if mac != "ff:ff:ff:ff:ff:ff":
                macs.add(mac)
    return macs


def overlay_aps(
    observations: list[dict[str, Any]],
    ap_associated: dict[str, dict[str, str]],
    router_name: str,
) -> list[dict[str, Any]]:
    """Attribute each observation to the access point it's connected to.

    - Devices associated to one of the main router's own radios (interface set
      by `merge_observations`) get `ap = router_name`.
    - Devices found in a configured AP's association list get `ap = <AP name>`
      (this wins — it's where the device physically is).
    - Everything else (seen only via the bridge table) keeps `ap = None`
      ("behind an AP", which one unknown).

    `ap_associated` maps AP name -> {mac: interface}. Pure function.
    """
    by_mac: dict[str, dict[str, Any]] = {}
    for o in observations:
        item = dict(o)
        item.setdefault("ap", None)
        if item.get("interface") is not None and item["ap"] is None:
            item["ap"] = router_name
        by_mac[item["mac"]] = item

    for name, assoc in ap_associated.items():
        for mac, iface in assoc.items():
            item = by_mac.get(mac)
            if item is None:
                item = {
                    "mac": mac,
                    "ip": None,
                    "hostname": None,
                    "vendor": lookup_vendor(mac),
                }
                by_mac[mac] = item
            item["interface"] = iface
            item["ap"] = name
    return list(by_mac.values())


def merge_observations(
    present: dict[str, Optional[str]],
    ip_by_mac: dict[str, str],
    host_by_mac: dict[str, str],
) -> list[dict[str, Any]]:
    """Build the normalized observation list for currently-present devices.

    `present` maps every currently-present MAC to its wifi interface, or None
    when the device was seen via the bridge table rather than associated to one
    of the main router's own radios (e.g. it's behind an AP). The other maps
    just enrich each device with IP and hostname.
    """
    observations = []
    for mac, iface in present.items():
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


def tcp_check(host: str, port: int, timeout: float = 5.0) -> tuple[bool, Optional[str]]:
    """Can we open a TCP connection to host:port? Returns (ok, error_message).

    This separates "the host/port is unreachable" (network, firewall, wrong
    port, or the router's SSH brute-force protection silently dropping us) from
    "we reached SSH but login/commands failed". A plain `TimeoutError: timed
    out` from paramiko means this layer failed — the credentials were never
    even tried.
    """
    if not host:
        return False, "no host configured"
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


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

    def _associated(self, client: "paramiko.SSHClient", s: dict[str, Any]) -> dict[str, str]:
        """{mac: interface} for clients associated to this device's own radios."""
        ifaces = self._run(client, s["cmd_ifnames"]).split()
        associated: dict[str, str] = {}
        for iface in ifaces:
            cmd = s["cmd_assoclist"].format(iface=iface)
            associated.update(parse_assoclist(self._run(client, cmd), iface))
        return associated

    def fetch_clients(self) -> list[dict[str, Any]]:
        """Run the discovery commands and return normalized observations.

        Raises on connection/auth failure so the poller can apply backoff.
        """
        with self._lock:
            client = self._ensure_connection()
            s = self.settings

            associated = self._associated(client, s)

            # Bridge table catches devices behind APs / AiMesh nodes / switches
            # that never associate to the main router's own radios.
            fdb_macs: set[str] = set()
            if s.get("cmd_fdb"):
                fdb_macs = parse_fdb(self._run(client, s["cmd_fdb"]))

            ip_by_mac = parse_neigh(self._run(client, s["cmd_neigh"]))
            host_by_mac = parse_leases(self._run(client, s["cmd_leases"]))

        # Union: associated MACs keep their wifi interface; FDB-only MACs have
        # interface None (we don't know which AP they're on).
        present: dict[str, Optional[str]] = {m: None for m in fdb_macs}
        present.update(associated)
        return merge_observations(present, ip_by_mac, host_by_mac)

    def fetch_associated(self) -> dict[str, str]:
        """{mac: interface} for an access point — used to attribute clients to
        the AP they're connected to. Lighter than fetch_clients (no FDB/leases).
        """
        with self._lock:
            client = self._ensure_connection()
            return self._associated(client, self.settings)

    def test_connection(self) -> dict[str, Any]:
        """Used by the Settings 'Test connection' button.

        Probes in layers so the message says WHERE it failed:
        TCP reachability -> SSH/auth -> command. A bare "timed out" almost
        always means the TCP layer — the router is unreachable from this
        machine, the port is wrong/closed, or (common on ASUS) SSH brute-force
        protection has temporarily blocked this device's IP.
        """
        s = self.settings
        host = s.get("router_host", "")
        port = int(s.get("router_port", 22))

        ok, err = tcp_check(host, port, timeout=5.0)
        if not ok:
            return {
                "ok": False,
                "stage": "tcp",
                "error": (
                    f"Can't reach {host}:{port} ({err}). The router is "
                    f"unreachable from this machine, the SSH port is wrong or "
                    f"closed, or the router's SSH brute-force protection has "
                    f"temporarily blocked this device."
                ),
            }

        auth_exc = getattr(paramiko, "AuthenticationException", ()) if paramiko else ()
        try:
            with self._lock:
                client = self._ensure_connection()
                ifnames_out = self._run(client, s["cmd_ifnames"])
            return {"ok": True, "interfaces": ifnames_out.split()}
        except auth_exc as e:  # type: ignore[misc]
            return {
                "ok": False,
                "stage": "auth",
                "error": f"Reached {host}:{port}, but SSH login failed — "
                f"check the username and password/key. ({e})",
            }
        except Exception as e:
            return {
                "ok": False,
                "stage": "ssh",
                "error": f"Reached {host}:{port}, but the SSH session failed: "
                f"{type(e).__name__}: {e}",
            }
