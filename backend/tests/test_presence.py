from backend.presence import compute_state

NOW = 1_000_000.0


def _device(mac, person_id=None, last_seen=NOW, ignored=False):
    return {
        "mac": mac,
        "person_id": person_id,
        "last_seen": last_seen,
        "ignored": ignored,
        "hostname": None,
        "ip": None,
        "vendor": None,
        "interface": None,
        "label": None,
        "is_present": 1,
    }


def test_person_home_if_any_device_active():
    people = [{"id": 1, "name": "Brother"}]
    devices = [
        _device("a", person_id=1, last_seen=NOW - 9999),  # stale phone (5G)
        _device("b", person_id=1, last_seen=NOW - 10),     # other phone present
    ]
    state = compute_state(people, devices, grace_seconds=600, now=NOW)
    assert state["people"][0]["home"] is True


def test_grace_window_keeps_recently_seen_home():
    people = [{"id": 1, "name": "Sister"}]
    # Seen 5 min ago, grace 10 min -> still home (covers brief wifi-off).
    devices = [_device("a", person_id=1, last_seen=NOW - 5 * 60)]
    state = compute_state(people, devices, grace_seconds=600, now=NOW)
    assert state["people"][0]["home"] is True


def test_beyond_grace_window_is_away():
    people = [{"id": 1, "name": "Sister"}]
    devices = [_device("a", person_id=1, last_seen=NOW - 11 * 60)]
    state = compute_state(people, devices, grace_seconds=600, now=NOW)
    person = state["people"][0]
    assert person["home"] is False
    assert person["last_seen"] == NOW - 11 * 60  # last-seen still reported


def test_ignored_devices_excluded():
    people = [{"id": 1, "name": "Dad"}]
    devices = [_device("a", person_id=1, last_seen=NOW, ignored=True)]
    state = compute_state(people, devices, grace_seconds=600, now=NOW)
    assert state["people"][0]["home"] is False
    assert state["people"][0]["devices"] == []


def test_unassigned_present_listed():
    devices = [_device("x", person_id=None, last_seen=NOW)]
    state = compute_state([], devices, grace_seconds=600, now=NOW)
    assert len(state["unassigned_present"]) == 1
    assert state["unassigned_present"][0]["mac"] == "x"
