# WiFi Presence Monitor — Design

Date: 2026-05-28

## Goal

A live web page showing **who is home and who isn't**, derived from devices
connected/visible to a home ASUS router. Robust against:

- Many irrelevant devices in the house (must be filterable).
- Family members owning multiple phones (group devices under a person).
- A device temporarily dropping off wifi (e.g. switching to 5G) — must not
  instantly flap to "away".

Runs continuously on an always-on home server / Raspberry Pi.

## Stack

- **Backend:** Python, FastAPI, paramiko (SSH), SQLite, asyncio background poller.
- **Frontend:** Vite + React SPA, talking to the backend via REST + WebSocket.
- **Persistence:** SQLite (all settings, mappings, and device records survive restarts).

## Router Data Source (low-impact)

SSH into the ASUS router on a configurable interval (**default 30s**) over a
**single reused connection** (paramiko transport kept alive with keepalive —
no reconnect per cycle). Each cycle runs one cheap combined command set:

1. **Associated wifi clients** — for each wireless interface (auto-discovered
   via `nvram get wl_ifnames`): `wl -i <iface> assoclist`. These MACs are
   *actively associated to wifi right now* — the strongest "present" signal.
2. **Neighbor/ARP table** — `ip neigh show` (fallback `cat /proc/net/arp`) for
   IP↔MAC enrichment.
3. **DHCP leases** — `cat /var/lib/misc/dnsmasq.leases` for hostnames.

This mirrors Home Assistant's proven AsusWRT integration approach and imposes
negligible load on the router. Works on stock Asuswrt and Asuswrt-Merlin. The
exact commands are stored in Settings so they can be overridden if a given
firmware differs.

### MAC randomization

Modern iOS/Android devices use a per-SSID randomized "private" MAC. On the home
SSID this MAC is **stable**, so once a device is mapped to a person it stays
mapped. The Devices UI surfaces unknown MACs with vendor (OUI) and hostname
hints to make first-time assignment easy.

## Presence Logic

- Every poll updates each observed device's `last_seen` timestamp and current
  `is_present` flag (present = seen this cycle).
- **Grace window** (configurable, **default 10 min**): a device is considered
  "still here" until it has been unseen for longer than the grace window.
- **A person is HOME** if **any** of their assigned devices is within the grace
  window. This is what gracefully handles:
  - Multiple phones (any one present ⇒ person home).
  - The 5G/wifi-off blip (brief disappearance < grace window ⇒ stays home).
- When a person flips to AWAY, the UI shows the **last-seen** time
  ("last seen 14 min ago").

## Components

1. **Poller** (`backend/poller.py`) — async task: SSH → run commands → parse →
   upsert device observations into SQLite. Owns the reused SSH connection and
   reconnects with backoff on failure.
2. **Router client** (`backend/router.py`) — wraps paramiko; exposes
   `fetch_clients()` returning a normalized list of observations
   `{mac, ip, hostname, interface, present}`. Pure parsing logic separated for
   testability.
3. **Presence engine** (`backend/presence.py`) — pure function: given devices
   (+ last_seen), people, mappings, and grace window → per-person presence
   state. No I/O, fully unit-testable.
4. **Store** (`backend/store.py`) — SQLite access layer (people, devices,
   mappings, settings). Single source of truth.
5. **OUI vendor lookup** (`backend/oui.py`) — bundled offline MAC-prefix →
   vendor map (no external network calls), best-effort.
6. **API app** (`backend/app.py`) — FastAPI: REST endpoints + a WebSocket that
   broadcasts the computed presence state after every poll cycle. Serves the
   built React SPA in production.
7. **Frontend** (`frontend/`) — Vite + React SPA.

## Data Model (SQLite)

- `people(id, name, created_at)`
- `devices(mac PK, hostname, ip, vendor, interface, first_seen, last_seen,
  is_present, person_id NULLABLE, ignored BOOL, label)`
- `settings(key PK, value)` — router host/port/user/auth, poll_interval,
  grace_minutes, command overrides.

`person_id` on `devices` implements the people-own-devices mapping (a device
belongs to at most one person). `ignored` removes irrelevant devices from view.

## API (sketch)

- `GET  /api/state` — current people presence + present unassigned devices.
- `WS   /api/ws` — pushes the same state object on every poll cycle.
- `GET  /api/devices` — all known devices (with filters).
- `PATCH /api/devices/{mac}` — assign person / set label / set ignored.
- `GET/POST/PATCH/DELETE /api/people` — manage people.
- `GET/PUT /api/settings` — read/update settings (router creds, intervals).
- `POST /api/router/test` — test SSH connection from Settings UI.

## Frontend Views

- **Dashboard (live):** person cards (home/away, contributing device(s),
  last-seen, signal if available). Updates via WebSocket. A tray shows
  present-but-unassigned devices for quick triage.
- **Devices:** table of every seen MAC — hostname, vendor, IP, last-seen,
  present indicator. Inline assign-to-person and an **Ignore** toggle.
- **People:** create / rename / delete people; see/assign their devices.
- **Settings:** router SSH host/port/user/password-or-key, poll interval, grace
  window, advanced command overrides; a "Test connection" button. All persisted.

## YAGNI / Out of Scope

- No authentication (LAN-local, single household).
- No long-term history charts — only current state + last-seen.
- No external API calls (OUI vendor data bundled offline).
- No multi-router support (single ASUS router).

## Testing

- Unit tests for parsers (`router.py`) against captured command output samples.
- Unit tests for the presence engine (`presence.py`) covering: any-device-home,
  grace-window boundary, all-away, ignored devices excluded.
- Store round-trip tests (settings/mappings persist).
