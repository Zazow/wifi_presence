# WiFi Presence Monitor

A live web page showing **who's home and who isn't**, based on the devices
connected to your home ASUS router (SSH). Built for an always-on home server /
Raspberry Pi.

## How it works

A background poller SSHes into the router every ~30s over a single reused
connection (low impact), reads the associated wifi clients (`wl assoclist`) plus
ARP and DHCP leases, and stores observations in SQLite. A person is **home** if
**any** of their assigned devices was seen within a configurable **grace
window** (default 10 min) — which is what makes it tolerant of:

- people owning multiple phones (any one present ⇒ home), and
- someone briefly turning off wifi (e.g. to use 5G) — a short gap stays "home"
  until the grace window lapses, then flips to "away · last seen 12 min ago".

All settings and device↔person mappings live in the SQLite file, so they
survive restarts.

## Requirements

- An ASUS router with **SSH enabled** (LAN > Administration > Service in the
  router UI). Works with stock Asuswrt and Asuswrt-Merlin.
- Python 3.11+ and Node 18+ on the host.

## Setup

```bash
# Backend
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt

# Frontend (build the SPA once; FastAPI serves it)
cd frontend && npm install && npm run build && cd ..
```

## Run

One command, production mode (builds the frontend and serves everything from a
single process — what you'd run on the always-on server/Pi):

```bash
./start.sh            # serves on http://0.0.0.0:8000  (override with PORT=...)
```

Or run the backend directly:

```bash
.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Open `http://<host>:8000`. Go to **Settings**, enter the router host, SSH
username and password (or an SSH key path), and click **Test Connection**. Once
connected, devices appear under **Devices** — assign each phone to a **Person**
(create people there or in the **People** tab), and **Ignore** the clutter
(IoT, etc.). The **Dashboard** then shows live home/away status.

Data & settings:
- All settings and device↔person mappings are stored in a SQLite database at a
  **stable absolute path**: `data/wifi_presence.db` (next to the project). This
  is what survives restarts — back up this file to preserve your config.
- Override the location with the `WIFI_PRESENCE_DB` env var (recommended for
  systemd; see the unit below). The path is resolved absolutely, so the server
  always opens the same database no matter which directory you launch it from.

### Run as a service (systemd, on a Pi/server)

```ini
# /etc/systemd/system/wifi-presence.service
[Unit]
Description=WiFi Presence Monitor
After=network-online.target

[Service]
WorkingDirectory=/path/to/wifi_presence
Environment=WIFI_PRESENCE_DB=/path/to/wifi_presence/wifi_presence.db
ExecStart=/path/to/wifi_presence/.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now wifi-presence
```

## Development

One command runs both the backend (auto-reload) and the Vite dev server:

```bash
./dev.sh              # then open http://localhost:5280  (Ctrl+C stops both)
```

Vite proxies `/api` and the WebSocket to the backend on :8000, so the UI hot-
reloads while the API stays live.

## Tests

```bash
.venv/bin/python -m pytest backend/tests -q
```

## Notes

- **Devices behind APs:** `wl assoclist` only reports clients on the *main
  router's own* radios. To also catch devices on separate access points or wired
  switches, the poller reads the router's bridge forwarding table
  (`brctl showmacs br0`) and treats those MACs as present too. Clear the *Bridge
  table command* in Settings → Advanced to disable this and go wifi-only.
- **Which AP a device is on:** add your bridge-/AP-mode access points under
  Settings → *Access points* (name + host + SSH login; blank login inherits the
  main router's). Each AP is polled over SSH for its association list, and
  devices are shown on the AP they're connected to. Devices on the main router
  show its name; devices behind an unlisted AP show "behind AP".
- **Refresh:** the Dashboard and Devices views have a Refresh button that forces
  an immediate poll instead of waiting for the next interval.
- **MAC randomization:** modern iPhones/Androids use a private MAC per SSID, but
  it's stable on your home wifi — once mapped, a device stays mapped.
- **Notes on commands:** if your firmware uses different paths, override the
  discovery commands under Settings → *Advanced: router commands*.
- LAN-local, single household: there is no authentication. Don't expose it to
  the internet.
