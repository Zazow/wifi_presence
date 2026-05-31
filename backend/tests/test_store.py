import json
import time
from pathlib import Path

from backend.store import (
    DEFAULT_DB_PATH,
    PROJECT_ROOT,
    Store,
    match_device_by_ip,
    normalize_ip,
    resolve_db_path,
)


def test_match_device_by_ip():
    devices = [
        {"mac": "aa", "ip": "192.168.1.5"},
        {"mac": "bb", "ip": "192.168.1.6"},
    ]
    assert match_device_by_ip(devices, "192.168.1.6")["mac"] == "bb"
    assert match_device_by_ip(devices, "192.168.1.9") is None
    assert match_device_by_ip(devices, "") is None


def test_match_device_by_ipv4_mapped_ipv6():
    # Dual-stack sockets report IPv4 clients as ::ffff:a.b.c.d — must still match.
    devices = [{"mac": "aa", "ip": "192.168.1.5"}]
    assert match_device_by_ip(devices, "::ffff:192.168.1.5")["mac"] == "aa"


def test_normalize_ip():
    assert normalize_ip("::ffff:192.168.1.5") == "192.168.1.5"
    assert normalize_ip("192.168.1.5") == "192.168.1.5"
    assert normalize_ip("::1") == "::1"  # loopback stays (server-local)
    assert normalize_ip("not-an-ip") == "not-an-ip"


def test_default_db_path_lives_outside_the_repo():
    # The production DB must NOT live inside the project working tree, or dev /
    # test / cleanup activity (rm, git clean) can delete the user's real data.
    p = resolve_db_path(None)
    assert p.is_absolute()
    assert p == DEFAULT_DB_PATH
    assert p.name == "wifi_presence.db"
    # Not under the repo.
    assert PROJECT_ROOT not in p.parents, f"{p} is inside the repo at {PROJECT_ROOT}"
    # In a dedicated per-user app directory.
    assert p.parent.name == "wifi-presence"


def test_db_path_override_resolves_absolute():
    p = resolve_db_path("~/some/where/wp.db")
    assert p.is_absolute()


def _store(tmp_path):
    return Store(tmp_path / "test.db")


def test_settings_persist_across_reopen(tmp_path):
    db = tmp_path / "test.db"
    s = Store(db)
    s.update_settings({"poll_interval": 45, "grace_minutes": 15})
    s.close()
    s2 = Store(db)
    settings = s2.get_settings()
    assert settings["poll_interval"] == 45
    assert settings["grace_minutes"] == 15


def test_mapping_persists_across_reopen(tmp_path):
    db = tmp_path / "test.db"
    s = Store(db)
    person = s.create_person("Brother")
    s.record_observations(
        [{"mac": "aa:bb:cc:dd:ee:ff", "ip": "192.168.1.5", "hostname": "phone",
          "interface": "eth6", "vendor": "Apple"}],
        time.time(),
    )
    s.update_device("aa:bb:cc:dd:ee:ff", {"person_id": person["id"], "label": "iPhone"})
    s.close()

    s2 = Store(db)
    dev = s2.get_device("aa:bb:cc:dd:ee:ff")
    assert dev["person_id"] == person["id"]
    assert dev["label"] == "iPhone"


def test_record_observations_marks_absent(tmp_path):
    s = _store(tmp_path)
    now = time.time()
    s.record_observations([{"mac": "a"}, {"mac": "b"}], now)
    s.record_observations([{"mac": "a"}], now + 1)  # b dropped off
    devices = {d["mac"]: d for d in s.list_devices()}
    assert devices["a"]["is_present"] == 1
    assert devices["b"]["is_present"] == 0
    assert devices["b"]["last_seen"] == now  # preserved for grace window


def test_delete_person_unassigns_devices(tmp_path):
    s = _store(tmp_path)
    p = s.create_person("X")
    s.record_observations([{"mac": "a"}], time.time())
    s.update_device("a", {"person_id": p["id"]})
    s.delete_person(p["id"])
    assert s.get_device("a")["person_id"] is None


def test_present_since_tracks_connection_streak(tmp_path):
    s = _store(tmp_path)
    t0 = 1000.0
    # First sighting -> present_since = t0.
    s.record_observations([{"mac": "a"}], t0)
    assert s.get_device("a")["present_since"] == t0
    # Still present a cycle later -> present_since unchanged (continuous streak).
    s.record_observations([{"mac": "a"}], t0 + 30)
    assert s.get_device("a")["present_since"] == t0
    # Disconnects -> streak cleared.
    s.record_observations([], t0 + 60)
    dev = s.get_device("a")
    assert dev["is_present"] == 0
    assert dev["present_since"] is None
    # Reconnects -> new streak starts at the reconnect time.
    s.record_observations([{"mac": "a"}], t0 + 90)
    assert s.get_device("a")["present_since"] == t0 + 90


def test_enrichment_not_wiped_by_missing_values(tmp_path):
    s = _store(tmp_path)
    now = time.time()
    s.record_observations(
        [{"mac": "a", "hostname": "phone", "ip": "192.168.1.5"}], now
    )
    # Next cycle sees the MAC associated but without hostname/ip enrichment.
    s.record_observations([{"mac": "a"}], now + 1)
    dev = s.get_device("a")
    assert dev["hostname"] == "phone"
    assert dev["ip"] == "192.168.1.5"


# ---- config backup / restore -------------------------------------------------
def test_backup_written_next_to_db_on_change(tmp_path):
    s = Store(tmp_path / "test.db")
    p = s.create_person("Brother")
    s.update_settings({"router_host": "10.0.0.9", "router_password": "secret"})
    s.record_observations([{"mac": "aa:bb"}], time.time())
    s.update_device("aa:bb", {"person_id": p["id"], "label": "iPhone"})

    backup = tmp_path / "wifi-presence-config-backup.json"
    assert backup.exists(), "a config backup should be written beside the DB"
    data = json.loads(backup.read_text())
    assert data["settings"]["router_host"] == "10.0.0.9"
    assert data["settings"]["router_password"] == "secret"  # full restore
    assert "Brother" in [pp["name"] for pp in data["people"]]
    mapping = {m["mac"]: m for m in data["device_map"]}
    assert mapping["aa:bb"]["person_name"] == "Brother"
    assert mapping["aa:bb"]["label"] == "iPhone"


def test_fresh_db_restores_from_backup(tmp_path):
    # Configure, then simulate the DB file being lost while the backup survives.
    db = tmp_path / "test.db"
    s = Store(db)
    p = s.create_person("Mom")
    s.update_settings({"router_host": "10.0.0.5", "router_password": "pw"})
    s.record_observations([{"mac": "cc:dd"}], time.time())
    s.update_device("cc:dd", {"person_id": p["id"], "label": "iPad", "ignored": True})
    s.close()

    db.unlink()  # DB gone; backup json remains beside it
    s2 = Store(db)  # fresh DB -> should auto-restore from backup
    assert s2.get_settings()["router_host"] == "10.0.0.5"
    assert s2.get_settings()["router_password"] == "pw"
    people = {pp["name"]: pp["id"] for pp in s2.list_people()}
    assert "Mom" in people
    dev = s2.get_device("cc:dd")
    assert dev["person_id"] == people["Mom"]
    assert dev["label"] == "iPad"
    assert dev["ignored"] == 1


def test_no_restore_when_db_already_has_data(tmp_path):
    # An existing populated DB must never be overwritten by an older backup.
    db = tmp_path / "test.db"
    s = Store(db)
    s.update_settings({"router_host": "1.1.1.1"})
    s.close()
    # Hand-write a stale backup with different data.
    (tmp_path / "wifi-presence-config-backup.json").write_text(
        json.dumps({"settings": {"router_host": "9.9.9.9"}, "people": [], "device_map": []})
    )
    s2 = Store(db)  # DB already existed and has data -> keep it
    assert s2.get_settings()["router_host"] == "1.1.1.1"
