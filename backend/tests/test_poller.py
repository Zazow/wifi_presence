"""Poller cycle tests.

These pin down the refresh behavior: a single poll cycle must broadcast updated
state on success, and must NOT die when the router (or anything else in the
cycle) raises — otherwise live updates stop forever.
"""
import asyncio

from backend.poller import Poller
from backend.store import Store


class FakeRouter:
    def __init__(self, obs=None, raise_exc=None):
        self.obs = obs or []
        self.raise_exc = raise_exc

    def fetch_clients(self):
        if self.raise_exc:
            raise self.raise_exc
        return self.obs

    def update_settings(self, s):
        pass

    def close(self):
        pass


def _poller(tmp_path, router):
    store = Store(tmp_path / "t.db")
    captured = []

    async def bcast(state):
        captured.append(state)

    p = Poller(store, bcast)
    p.router = router
    return p, captured


def test_poll_cycle_broadcasts_devices_on_success(tmp_path):
    router = FakeRouter(
        obs=[{"mac": "aa:bb:cc:dd:ee:01", "ip": "192.168.1.9",
              "hostname": "phone", "interface": "eth6", "vendor": "Apple"}]
    )
    p, captured = _poller(tmp_path, router)
    state = asyncio.run(p._run_cycle())
    assert p.last_error is None
    assert p.last_poll is not None
    assert captured[-1] is state
    macs = [d["mac"] for d in state["unassigned_present"]]
    assert "aa:bb:cc:dd:ee:01" in macs


def test_poll_cycle_survives_router_error(tmp_path):
    p, captured = _poller(tmp_path, FakeRouter(raise_exc=RuntimeError("ssh boom")))
    state = asyncio.run(p._run_cycle())
    assert "ssh boom" in (p.last_error or "")
    # Even on failure we still broadcast, so the UI shows the error/last-known.
    assert captured and captured[-1] is state


def test_poll_cycle_survives_broadcast_error(tmp_path):
    # A throwing broadcast must not propagate out of a cycle and kill the loop.
    store = Store(tmp_path / "t.db")

    async def bad_bcast(state):
        raise RuntimeError("ws boom")

    p = Poller(store, bad_bcast)
    p.router = FakeRouter(obs=[])
    # Should not raise.
    asyncio.run(p._run_cycle())
