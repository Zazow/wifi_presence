from backend.notify import enabled, message_for, presence_transitions


def test_transitions_detect_arrive_and_leave():
    prev = {1: True, 2: False, 3: True}
    curr = {1: False, 2: True, 3: True}
    out = {t["person_id"]: t["event"] for t in presence_transitions(prev, curr)}
    assert out == {1: "left", 2: "arrived"}  # 3 unchanged -> omitted


def test_no_transition_for_new_person_or_first_run():
    # Person 9 wasn't in prev -> no spurious notification on first sight.
    assert presence_transitions({}, {9: True}) == []
    assert presence_transitions({1: True}, {1: True, 9: False}) == []


def test_enabled_requires_a_channel():
    assert enabled({}) is False
    assert enabled({"notify_ntfy_url": "", "notify_webhook_url": ""}) is False
    assert enabled({"notify_ntfy_url": "https://ntfy.sh/x"}) is True
    assert enabled({"notify_webhook_url": "https://example.com/hook"}) is True


def test_message_wording():
    assert message_for("Mom", "arrived") == "Mom arrived home"
    assert message_for("Dad", "left") == "Dad left"
