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
from .router import RouterClient
from .store import Store


class Poller:
    def __init__(self, store: Store, broadcast: Callable[[dict[str, Any]], "asyncio.Future | Any"]):
        self.store = store
        self.broadcast = broadcast
        self.router = RouterClient(self.store.get_settings())
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self.last_state: dict[str, Any] = {"people": [], "unassigned_present": []}
        self.last_error: Optional[str] = None
        self.last_poll: Optional[float] = None

    def reload_router_settings(self) -> None:
        self.router.update_settings(self.store.get_settings())

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
        self.router.close()

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

    async def _loop(self) -> None:
        backoff = 5
        while not self._stop.is_set():
            settings = self.store.get_settings()
            interval = max(5, int(settings.get("poll_interval", 30)))
            try:
                observations = await asyncio.to_thread(self.router.fetch_clients)
                self.store.record_observations(observations, time.time())
                self.last_error = None
                self.last_poll = time.time()
                backoff = 5
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"

            # Recompute + broadcast regardless, so the UI reflects grace-window
            # expiries even while the router is briefly unreachable.
            state = self.current_state()
            self.last_state = state
            result = self.broadcast(state)
            if asyncio.iscoroutine(result):
                await result

            wait = interval if self.last_error is None else min(backoff, 60)
            if self.last_error is not None:
                backoff = min(backoff * 2, 60)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass
