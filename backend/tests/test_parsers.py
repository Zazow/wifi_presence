from backend.router import (
    merge_observations,
    parse_assoclist,
    parse_fdb,
    parse_leases,
    parse_neigh,
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
