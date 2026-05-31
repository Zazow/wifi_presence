import { useEffect, useState } from "react";
import { api } from "../api";
import { timeAgo, deviceName, durationSince, clockTime } from "../util";
import type { Device, DevicePatch, Person } from "../types";
import RefreshButton from "../components/RefreshButton";
import RegisterDeviceModal from "../components/RegisterDeviceModal";

type Filter = "active" | "unassigned" | "all" | "ignored";
const FILTERS: Filter[] = ["active", "unassigned", "all", "ignored"];

export default function Devices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [filter, setFilter] = useState<Filter>("active");
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

  async function patch(mac: string, body: DevicePatch) {
    await api.patchDevice(mac, body);
    refresh();
  }

  const visible = devices
    .filter((d) => {
      if (filter === "ignored") return Boolean(d.ignored);
      if (d.ignored) return false;
      if (filter === "unassigned") return d.person_id == null;
      if (filter === "active") return Boolean(d.is_present);
      return true;
    })
    .sort((a, b) => (b.last_seen ?? 0) - (a.last_seen ?? 0));

  if (loading) return <div className="loading">Loading devices…</div>;

  return (
    <div className="devices">
      <div className="toolbar">
        <div className="segmented">
          {FILTERS.map((f) => (
            <button
              key={f}
              className={filter === f ? "seg active" : "seg"}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
        <div className="toolbar-right">
          <span className="muted small">{visible.length} shown</span>
          <button className="btn btn-primary" onClick={() => setShowRegister(true)}>
            + Register this device
          </button>
          <RefreshButton onDone={refresh} />
        </div>
      </div>

      {showRegister && (
        <RegisterDeviceModal onClose={() => setShowRegister(false)} onDone={refresh} />
      )}

      <div className="table-card">
        <table className="grid">
          <thead>
            <tr>
              <th>Device</th>
              <th>Vendor</th>
              <th>Access point</th>
              <th>IP</th>
              <th>Connected</th>
              <th>Last seen</th>
              <th>Person</th>
              <th aria-label="actions"></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((d) => (
              <tr key={d.mac} className={d.is_present ? "present" : ""}>
                <td>
                  <div className="dev-name">
                    <span className={`status-dot ${d.is_present ? "on" : "off"}`} />
                    {deviceName(d)}
                  </div>
                  <div className="muted mono tiny">{d.mac}</div>
                </td>
                <td>{d.vendor || "—"}</td>
                <td className="small">{d.ap || (d.is_present ? "behind AP" : "—")}</td>
                <td className="mono small">{d.ip || "—"}</td>
                <td className="small" title={d.present_since ? `since ${clockTime(d.present_since)}` : ""}>
                  {d.is_present && d.present_since ? durationSince(d.present_since) : "—"}
                </td>
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
                    className="btn-link"
                    onClick={() => patch(d.mac, { ignored: !d.ignored })}
                  >
                    {d.ignored ? "unignore" : "ignore"}
                  </button>
                </td>
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td colSpan={8} className="muted center pad">
                  No devices in this view.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
