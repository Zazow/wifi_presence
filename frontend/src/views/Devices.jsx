import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { timeAgo, deviceName } from "../util.js";
import RefreshButton from "../components/RefreshButton.jsx";
import RegisterDeviceModal from "../components/RegisterDeviceModal.jsx";

export default function Devices() {
  const [devices, setDevices] = useState([]);
  const [people, setPeople] = useState([]);
  const [filter, setFilter] = useState("active"); // active | all | unassigned | ignored
  const [loading, setLoading] = useState(true);
  const [showRegister, setShowRegister] = useState(false);

  async function refresh() {
    const [d, p] = await Promise.all([api.listDevices(), api.listPeople()]);
    setDevices(d);
    setPeople(p);
    setLoading(false);
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  async function patch(mac, body) {
    await api.patchDevice(mac, body);
    refresh();
  }

  const visible = devices
    .filter((d) => {
      if (filter === "ignored") return d.ignored;
      if (d.ignored) return false;
      if (filter === "unassigned") return d.person_id == null;
      if (filter === "active") return d.is_present;
      return true;
    })
    .sort((a, b) => (b.last_seen || 0) - (a.last_seen || 0));

  if (loading) return <div className="loading">Loading devices…</div>;

  return (
    <div className="devices">
      <div className="toolbar">
        <div className="filters">
          {["active", "unassigned", "all", "ignored"].map((f) => (
            <button
              key={f}
              className={filter === f ? "active" : ""}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="toolbar-right">
          <span className="muted small">{visible.length} shown</span>
          <button className="register-btn" onClick={() => setShowRegister(true)}>
            + Register this device
          </button>
          <RefreshButton onDone={refresh} />
        </div>
      </div>

      {showRegister && (
        <RegisterDeviceModal
          onClose={() => setShowRegister(false)}
          onDone={refresh}
        />
      )}

      <table className="grid">
        <thead>
          <tr>
            <th>Device</th>
            <th>Vendor</th>
            <th>AP</th>
            <th>IP</th>
            <th>Last seen</th>
            <th>Person</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {visible.map((d) => (
            <tr key={d.mac} className={d.is_present ? "present" : ""}>
              <td>
                <div className="dev-name">
                  <span className={`dot ${d.is_present ? "green" : "grey"}`} />
                  {deviceName(d)}
                </div>
                <div className="muted mono small">{d.mac}</div>
              </td>
              <td>{d.vendor || "—"}</td>
              <td className="small">{d.ap || (d.is_present ? "behind AP" : "—")}</td>
              <td className="mono small">{d.ip || "—"}</td>
              <td className="small">{timeAgo(d.last_seen)}</td>
              <td>
                <select
                  value={d.person_id ?? ""}
                  onChange={(e) =>
                    e.target.value === ""
                      ? patch(d.mac, { unassign: true })
                      : patch(d.mac, { person_id: Number(e.target.value) })
                  }
                >
                  <option value="">— unassigned —</option>
                  {people.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <button
                  className="link"
                  onClick={() => patch(d.mac, { ignored: !d.ignored })}
                >
                  {d.ignored ? "unignore" : "ignore"}
                </button>
              </td>
            </tr>
          ))}
          {visible.length === 0 && (
            <tr>
              <td colSpan={7} className="muted center">
                No devices in this view.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
