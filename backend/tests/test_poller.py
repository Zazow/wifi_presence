"""Poller cycle tests.

These pin down the refresh behavior: a single poll cycle must broadcast updated
state on success, and must NOT die when the router (or anything else in the
cycle) raises — otherwise live updates stop forever.
"""
import asyncio

from backend.poller import Poller
from backend.store import Store


class FakeRouter:
    def __init__(self, associated=None, fdb=None, ip_by_mac=None, host_by_mac=None, raise_exc=None):
        self.associated = associated or {}
        self.fdb = fdb or set()
        self.ip_by_mac = ip_by_mac or {}
        self.host_by_mac = host_by_mac or {}
        self.raise_exc = raise_exc

    def fetch_raw(self):
        if self.raise_exc:
            raise self.raise_exc
        return {
            "associated": self.associated,
            "fdb": self.fdb,
            "ip_by_mac": self.ip_by_mac,
            "host_by_mac": self.host_by_mac,
        }

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
        associated={"aa:bb:cc:dd:ee:01": "eth6"},
        ip_by_mac={"aa:bb:cc:dd:ee:01": "192.168.1.9"},
        host_by_mac={"aa:bb:cc:dd:ee:01": "phone"},
    )
    p, captured = _poller(tmp_path, router)
    state = asyncio.run(p._run_cycle())
    assert p.last_error is None
    assert p.last_poll is not None
    assert captured[-1] is state
    macs = [d["mac"] for d in state["unassigned_present"]]
    assert "aa:bb:cc:dd:ee:01" in macs


def test_poll_cycle_drops_wifi_device_lingering_in_fdb(tmp_path):
    # Cycle 1: phone associated to the main router -> learns its wifi interface.
    p, _ = _poller(tmp_path, FakeRouter(associated={"aa:bb:cc:dd:ee:01": "eth6"}))
    asyncio.run(p._run_cycle())
    assert p.store.get_device("aa:bb:cc:dd:ee:01")["is_present"] == 1

    # Cycle 2: phone disconnected (gone from assoclist) but still in bridge FDB.
    # It must NOT be marked present again.
    p.router = FakeRouter(associated={}, fdb={"aa:bb:cc:dd:ee:01"})
    asyncio.run(p._run_cycle())
    assert p.store.get_device("aa:bb:cc:dd:ee:01")["is_present"] == 0


def test_poll_cycle_survives_router_error(tmp_path):
    p, captured = _poller(tmp_path, FakeRouter(raise_exc=RuntimeError("ssh boom")))
    state = asyncio.run(p._run_cycle())
    assert "ssh boom" in (p.last_error or "")
    # Even on failure we still broadcast, so the UI shows the error/last-known.
    assert captured and captured[-1] is state


def test_test_all_covers_main_and_each_ap(tmp_path):
    store = Store(tmp_path / "t.db")
    store.update_settings(
        {
            "router_host": "127.0.0.1",
            "router_port": 9,  # nothing listening -> fast, deterministic failure
            "router_name": "Main",
            "access_points": [
                {"name": "Upstairs", "host": "127.0.0.1", "port": 9,
                 "user": "", "password": "", "key_path": ""}
            ],
        }
    )

    async def bcast(state):
        pass

    p = Poller(store, bcast)
    out = asyncio.run(p.test_all())
    names = {r["name"] for r in out["results"]}
    assert names == {"Main", "Upstairs"}  # main router + the AP both tested
    assert all(r["ok"] is False and r["stage"] == "tcp" for r in out["results"])


def test_poll_cycle_survives_broadcast_error(tmp_path):
    # A throwing broadcast must not propagate out of a cycle and kill the loop.
    store = Store(tmp_path / "t.db")

    async def bad_bcast(state):
        raise RuntimeError("ws boom")

    p = Poller(store, bad_bcast)
    p.router = FakeRouter()
    # Should not raise.
    asyncio.run(p._run_cycle())
