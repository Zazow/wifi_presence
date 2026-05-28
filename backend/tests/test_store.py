import time

from backend.store import DEFAULT_DB_PATH, Store, resolve_db_path


def test_default_db_path_is_absolute_and_cwd_independent():
    p = resolve_db_path(None)
    assert p.is_absolute()
    assert p == DEFAULT_DB_PATH
    assert p.name == "wifi_presence.db"
    # Lives in a dedicated data dir, not as a stray file at an arbitrary cwd.
    assert p.parent.name == "data"


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
