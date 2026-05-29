import socket

from backend.router import (
    RouterClient,
    merge_observations,
    overlay_aps,
    parse_assoclist,
    parse_fdb,
    parse_leases,
    parse_neigh,
    tcp_check,
)


def test_parse_assoclist():
    out = "assoclist AA:BB:CC:DD:EE:FF\nassoclist 11:22:33:44:55:66\n"
    result = parse_assoclist(out, "eth6")
    assert result == {
        "aa:bb:cc:dd:ee:ff": "eth6",
        "11:22:33:44:55:66": "eth6",
    }


def test_parse_assoclist_ignores_noise():
    assert parse_assoclist("no clients here\n", "eth1") == {}


def test_parse_neigh_ip_neigh_format():
    out = (
        "192.168.1.23 dev br0 lladdr aa:bb:cc:dd:ee:ff REACHABLE\n"
        "192.168.1.99 dev br0 lladdr 11:22:33:44:55:66 STALE\n"
        "192.168.1.5 dev br0 FAILED\n"
    )
    result = parse_neigh(out)
    assert result["aa:bb:cc:dd:ee:ff"] == "192.168.1.23"
    assert result["11:22:33:44:55:66"] == "192.168.1.99"
    assert len(result) == 2  # FAILED row skipped


def test_parse_neigh_proc_arp_format():
    out = (
        "IP address       HW type     Flags       HW address            Mask     Device\n"
        "192.168.1.23     0x1         0x2         aa:bb:cc:dd:ee:ff     *        br0\n"
    )
    assert parse_neigh(out) == {"aa:bb:cc:dd:ee:ff": "192.168.1.23"}


def test_parse_leases():
    out = (
        "1700000000 aa:bb:cc:dd:ee:ff 192.168.1.23 Ziyad-iPhone 01:aa:bb\n"
        "1700000000 11:22:33:44:55:66 192.168.1.99 * *\n"
    )
    result = parse_leases(out)
    assert result == {"aa:bb:cc:dd:ee:ff": "Ziyad-iPhone"}


def test_parse_fdb_brctl():
    out = (
        "port no\tmac addr\t\tis local?\tageing timer\n"
        "  1\taa:bb:cc:dd:ee:ff\tno\t\t   1.23\n"
        "  2\t11:22:33:44:55:66\tyes\t\t   0.00\n"  # local bridge port, skip
        "  3\t99:88:77:66:55:44\tno\t\t  42.10\n"
    )
    result = parse_fdb(out)
    assert result == {"aa:bb:cc:dd:ee:ff", "99:88:77:66:55:44"}


def test_parse_fdb_iproute2():
    out = (
        "aa:bb:cc:dd:ee:ff dev eth6 master br0\n"
        "33:33:00:00:00:01 dev eth0 self permanent\n"
        "11:22:33:44:55:66 dev eth7 master br0\n"
    )
    result = parse_fdb(out)
    assert result == {"aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66"}


def test_merge_observations():
    present = {"aa:bb:cc:dd:ee:ff": "eth6"}
    ips = {"aa:bb:cc:dd:ee:ff": "192.168.1.23"}
    hosts = {"aa:bb:cc:dd:ee:ff": "Ziyad-iPhone"}
    obs = merge_observations(present, ips, hosts)
    assert len(obs) == 1
    o = obs[0]
    assert o["mac"] == "aa:bb:cc:dd:ee:ff"
    assert o["ip"] == "192.168.1.23"
    assert o["hostname"] == "Ziyad-iPhone"
    assert o["interface"] == "eth6"


def test_merge_observations_ap_device_has_no_interface():
    # A device seen only via the bridge table (behind an AP) has interface None.
    present = {"aa:bb:cc:dd:ee:ff": None}
    obs = merge_observations(present, {}, {"aa:bb:cc:dd:ee:ff": "Phone"})
    assert obs[0]["interface"] is None
    assert obs[0]["hostname"] == "Phone"


def test_overlay_aps_attributes_main_and_ap():
    observations = [
        # associated to the main router (interface set)
        {"mac": "aa:aa:aa:aa:aa:aa", "interface": "eth6", "ip": None,
         "hostname": None, "vendor": "Apple"},
        # seen only via bridge table (behind some AP, interface None)
        {"mac": "bb:bb:bb:bb:bb:bb", "interface": None, "ip": None,
         "hostname": None, "vendor": None},
    ]
    ap_assoc = {"Upstairs": {"bb:bb:bb:bb:bb:bb": "eth7"}}
    out = {o["mac"]: o for o in overlay_aps(observations, ap_assoc, "Main router")}
    assert out["aa:aa:aa:aa:aa:aa"]["ap"] == "Main router"
    assert out["bb:bb:bb:bb:bb:bb"]["ap"] == "Upstairs"
    assert out["bb:bb:bb:bb:bb:bb"]["interface"] == "eth7"


def test_overlay_aps_adds_ap_only_device():
    # Device the AP sees but the main router didn't report at all.
    out = overlay_aps([], {"Garage": {"cc:cc:cc:cc:cc:cc": "eth6"}}, "Main router")
    assert out[0]["mac"] == "cc:cc:cc:cc:cc:cc"
    assert out[0]["ap"] == "Garage"


def test_tcp_check_success_on_open_port():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        ok, err = tcp_check("127.0.0.1", port, timeout=2)
        assert ok is True and err is None
    finally:
        srv.close()


def test_tcp_check_failure_on_closed_port():
    # Reserved discard port that nothing listens on -> connection refused/timeout.
    ok, err = tcp_check("127.0.0.1", 9, timeout=2)
    assert ok is False
    assert err  # carries a reason


def test_tcp_check_no_host():
    ok, err = tcp_check("", 22)
    assert ok is False


def test_test_connection_reports_tcp_stage_when_unreachable():
    # No SSH server here; test_connection must classify it as a TCP failure
    # (not auth) and produce an actionable message.
    client = RouterClient({"router_host": "127.0.0.1", "router_port": 9})
    result = client.test_connection()
    assert result["ok"] is False
    assert result["stage"] == "tcp"
    assert "Can't reach" in result["error"]
