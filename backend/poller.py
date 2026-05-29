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

from .presence import compute_state
from .router import RouterClient, overlay_aps
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
        A failing AP contributes nothing rather than breaking the cycle."""
        async def one(name: str, client: RouterClient):
            try:
                return name, await asyncio.to_thread(client.fetch_associated)
            except Exception:
                return name, {}

        if not self.ap_clients:
            return {}
        results = await asyncio.gather(
            *(one(n, c) for n, c in self.ap_clients.items())
        )
        return dict(results)

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
        state = compute_state(people, devices, settings["grace_minutes"], time.time())
        state["status"] = {
            "last_poll": self.last_poll,
            "last_error": self.last_error,
        }
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
        try:
            observations = await asyncio.to_thread(self.router.fetch_clients)
            ap_assoc = await self._fetch_ap_assoc()
            router_name = self.store.get_settings().get("router_name", "Main router")
            observations = overlay_aps(observations, ap_assoc, router_name)
            self.store.record_observations(observations, time.time())
            self.last_error = None
            self.last_poll = time.time()
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"

        state = self.current_state()
        self.last_state = state
        await self._emit(state)
        return state

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
