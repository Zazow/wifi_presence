"""Async background poller.

Loops forever: read settings -> SSH fetch -> persist observations -> recompute
presence state -> broadcast to WebSocket subscribers. Reconnect/backoff on
failure so a sleeping router or wrong credentials don't crash the loop. The SSH
work runs in a thread executor so it never blocks the event loop.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Optional

from . import notify
from .presence import compute_state
from .router import RouterClient, build_present, to_observations
from .store import Store


def _ap_settings(base: dict[str, Any], ap: dict[str, Any]) -> dict[str, Any]:
    """Settings for an access point: inherit the main router's commands and
    fall back to its credentials for any field the AP leaves blank."""
    s = dict(base)
    s["router_host"] = ap.get("host", "")
    s["router_port"] = ap.get("port") or base.get("router_port", 22)
    s["router_user"] = ap.get("user") or base.get("router_user", "")
    s["router_password"] = ap.get("password") or base.get("router_password", "")
    s["router_key_path"] = ap.get("key_path") or base.get("router_key_path", "")
    return s


class Poller:
    def __init__(self, store: Store, broadcast: Callable[[dict[str, Any]], "asyncio.Future | Any"]):
        self.store = store
        self.broadcast = broadcast
        self.router = RouterClient(self.store.get_settings())
        self.ap_clients: dict[str, RouterClient] = {}
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self.last_state: dict[str, Any] = {"people": [], "unassigned_present": []}
        self.last_error: Optional[str] = None
        self.last_poll: Optional[float] = None
        # Per-target poll health (main router + each AP), for the UI.
        self.main_status: dict[str, Any] = {"ok": None, "error": None, "clients": 0}
        self.ap_status: dict[str, dict[str, Any]] = {}
        # Previous per-person home flags, for arrive/leave notifications.
        self._prev_home: dict[int, bool] = {}
        self._rebuild_ap_clients(self.store.get_settings())

    def _rebuild_ap_clients(self, settings: dict[str, Any]) -> None:
        for client in self.ap_clients.values():
            client.close()
        clients: dict[str, RouterClient] = {}
        for ap in settings.get("access_points") or []:
            name = (ap.get("name") or ap.get("host") or "").strip()
            if not name or not ap.get("host"):
                continue
            clients[name] = RouterClient(_ap_settings(settings, ap))
        self.ap_clients = clients

    def reload_router_settings(self) -> None:
        settings = self.store.get_settings()
        self.router.update_settings(settings)
        self._rebuild_ap_clients(settings)

    async def _fetch_ap_assoc(self) -> dict[str, dict[str, str]]:
        """Poll every configured AP concurrently for its associated clients.
        A failing AP contributes nothing rather than breaking the cycle, and its
        reachability is recorded in ap_status for the UI."""
        status: dict[str, dict[str, Any]] = {}

        async def one(name: str, client: RouterClient):
            try:
                assoc = await asyncio.to_thread(client.fetch_associated)
                status[name] = {"ok": True, "error": None, "clients": len(assoc)}
                return name, assoc
            except Exception as e:
                status[name] = {"ok": False, "error": f"{type(e).__name__}: {e}", "clients": 0}
                return name, {}

        if not self.ap_clients:
            self.ap_status = {}
            return {}
        results = await asyncio.gather(
            *(one(n, c) for n, c in self.ap_clients.items())
        )
        self.ap_status = status
        return dict(results)

    async def test_all(self) -> dict[str, Any]:
        """Test the main router AND every configured AP, concurrently.

        Returns {"results": [{name, ok, stage?, interfaces?/error?}, ...]} so the
        Settings UI can show which targets connect and which don't.
        """
        self.reload_router_settings()
        settings = self.store.get_settings()

        async def run(name: str, client: RouterClient) -> dict[str, Any]:
            result = await asyncio.to_thread(client.test_connection)
            result["name"] = name
            return result

        targets: list[tuple[str, RouterClient]] = [
            (settings.get("router_name", "Main router"), self.router)
        ]
        targets += list(self.ap_clients.items())
        results = await asyncio.gather(*(run(n, c) for n, c in targets))
        return {"results": list(results)}

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
        self.router.close()
        for client in self.ap_clients.values():
            client.close()

    async def poll_now(self) -> dict[str, Any]:
        """Run one poll cycle immediately (the manual 'refresh' button)."""
        return await self._run_cycle()

    def current_state(self) -> dict[str, Any]:
        people = self.store.list_people()
        devices = self.store.list_devices()
        settings = self.store.get_settings()
        # Never let the grace window drop below the poll interval, or a device
        # that's still connected would flap to "away" between polls.
        poll_interval = int(settings.get("poll_interval", 15))
        grace_seconds = max(int(settings.get("grace_seconds", 30)), poll_interval)
        state = compute_state(people, devices, grace_seconds, time.time())
        state["status"] = {
            "last_poll": self.last_poll,
            "last_error": self.last_error,
        }
        # Per-target health: main router first, then each configured AP.
        aps = [{"name": settings.get("router_name", "Main router"), "role": "router", **self.main_status}]
        for name, st in self.ap_status.items():
            aps.append({"name": name, "role": "ap", **st})
        state["aps"] = aps
        return state

    async def _emit(self, state: dict[str, Any]) -> None:
        """Broadcast state, swallowing broadcast errors so they can't kill the
        poll loop (a single bad WebSocket must not stop live updates)."""
        try:
            result = self.broadcast(state)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            pass

    async def _run_cycle(self) -> dict[str, Any]:
        """One poll: SSH fetch -> persist -> recompute -> broadcast.

        Router/SSH failures are captured into last_error rather than raised, and
        we recompute + broadcast regardless so the UI reflects grace-window
        expiries even while the router is briefly unreachable.
        """
        # Main router fetch — its own try so a failure here doesn't stop us from
        # polling (and health-checking) the independent APs.
        raw: Optional[dict[str, Any]] = None
        try:
            raw = await asyncio.to_thread(self.router.fetch_raw)
            self.last_error = None
            self.main_status = {"ok": True, "error": None, "clients": len(raw["associated"])}
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.main_status = {"ok": False, "error": self.last_error, "clients": 0}

        # Always poll APs (records their reachability in ap_status for the UI).
        ap_assoc = await self._fetch_ap_assoc()

        # Only persist observations when the MAIN router responded. Recording on
        # a main-router failure would wrongly mark its still-connected clients
        # absent just because SSH was briefly unavailable.
        if raw is not None:
            router_name = self.store.get_settings().get("router_name", "Main router")
            present = build_present(
                raw["associated"],
                ap_assoc,
                raw["fdb"],
                self.store.known_wifi_macs(),
                router_name,
            )
            observations = to_observations(present, raw["ip_by_mac"], raw["host_by_mac"])
            self.store.record_observations(observations, time.time())
            self.last_poll = time.time()

        state = self.current_state()
        self.last_state = state
        await self._notify_transitions(state)
        await self._emit(state)
        return state

    async def _notify_transitions(self, state: dict[str, Any]) -> None:
        """Fire arrive/leave notifications for people whose home flag changed
        since the last cycle. No-ops on the first cycle and when unconfigured."""
        curr = {p["id"]: bool(p["home"]) for p in state.get("people", [])}
        names = {p["id"]: p["name"] for p in state.get("people", [])}
        prev = self._prev_home
        self._prev_home = curr
        if not prev:
            return
        settings = self.store.get_settings()
        if not notify.enabled(settings):
            return
        for t in notify.presence_transitions(prev, curr):
            name = names.get(t["person_id"], "Someone")
            try:
                await asyncio.to_thread(notify.send, settings, name, t["event"])
            except Exception:
                pass

    async def _loop(self) -> None:
        backoff = 5
        while not self._stop.is_set():
            interval = max(5, int(self.store.get_settings().get("poll_interval", 30)))
            # Belt-and-suspenders: nothing in a cycle should ever propagate out
            # and terminate the loop, or live updates would stop permanently.
            try:
                await self._run_cycle()
            except Exception as e:
                self.last_error = f"poller: {type(e).__name__}: {e}"

            wait = interval if self.last_error is None else min(backoff, 60)
            backoff = 5 if self.last_error is None else min(backoff * 2, 60)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass
