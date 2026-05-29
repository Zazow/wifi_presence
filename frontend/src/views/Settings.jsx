import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const FIELDS = [
  ["router_name", "Main router name (shown as its AP)", "text"],
  ["router_host", "Router host / IP", "text"],
  ["router_port", "SSH port", "number"],
  ["router_user", "SSH username", "text"],
  ["router_password", "SSH password", "password"],
  ["router_key_path", "SSH key path (optional, overrides password)", "text"],
  ["poll_interval", "Poll interval (seconds)", "number"],
  ["grace_minutes", "Away grace window (minutes)", "number"],
];

const AP_FIELDS = [
  ["name", "Name (e.g. Upstairs)", "text"],
  ["host", "Host / IP", "text"],
  ["port", "Port", "number"],
  ["user", "User", "text"],
  ["password", "Password", "password"],
];

const BLANK_AP = { name: "", host: "", port: 22, user: "", password: "", key_path: "" };

const ADVANCED = [
  ["cmd_ifnames", "Wireless interfaces command"],
  ["cmd_assoclist", "Assoc list command ({iface} placeholder)"],
  ["cmd_neigh", "Neighbour/ARP command"],
  ["cmd_leases", "DHCP leases command"],
  ["cmd_fdb", "Bridge table command (finds devices behind APs; blank = off)"],
];

export default function Settings() {
  const [form, setForm] = useState(null);
  const [saved, setSaved] = useState(false);
  const [test, setTest] = useState(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    api.getSettings().then(setForm);
  }, []);

  if (!form) return <div className="loading">Loading settings…</div>;

  const set = (k, v) => {
    setForm({ ...form, [k]: v });
    setSaved(false);
  };

  const aps = form.access_points || [];
  const setAps = (next) => set("access_points", next);
  const addAp = () => setAps([...aps, { ...BLANK_AP }]);
  const updateAp = (i, key, val) =>
    setAps(aps.map((ap, j) => (j === i ? { ...ap, [key]: val } : ap)));
  const removeAp = (i) => setAps(aps.filter((_, j) => j !== i));

  async function save(e) {
    e.preventDefault();
    const payload = { ...form };
    // Don't send back the redaction placeholder.
    if (payload.router_password === "********") delete payload.router_password;
    const updated = await api.putSettings(payload);
    setForm(updated);
    setSaved(true);
  }

  async function runTest() {
    setTest({ status: "testing" });
    // Persist first so the test uses current form values.
    const payload = { ...form };
    if (payload.router_password === "********") delete payload.router_password;
    await api.putSettings(payload);
    const result = await api.testRouter();
    setTest(result);
  }

  return (
    <form className="settings" onSubmit={save}>
      <p className="muted small">
        Settings are saved to the database and persist across restarts.
      </p>
      {FIELDS.map(([key, label, type]) => (
        <label key={key} className="field">
          <span>{label}</span>
          <input
            type={type}
            value={form[key] ?? ""}
            onChange={(e) =>
              set(key, type === "number" ? Number(e.target.value) : e.target.value)
            }
          />
        </label>
      ))}

      <div className="ap-section">
        <h2>Access points</h2>
        <p className="muted small">
          Add your bridge-mode / AP-mode access points so devices can be shown
          on the AP they're connected to. Each is polled over SSH for its client
          list. Blank user/password fall back to the main router's. Devices on an
          AP that isn't listed show as "behind AP".
        </p>
        {aps.map((ap, i) => (
          <div className="ap-row" key={i}>
            {AP_FIELDS.map(([key, label, type]) => (
              <label key={key} className="field">
                <span>{label}</span>
                <input
                  type={type}
                  value={ap[key] ?? ""}
                  onChange={(e) =>
                    updateAp(i, key, type === "number" ? Number(e.target.value) : e.target.value)
                  }
                />
              </label>
            ))}
            <button type="button" className="link danger" onClick={() => removeAp(i)}>
              remove
            </button>
          </div>
        ))}
        <button type="button" className="link" onClick={addAp}>
          + Add access point
        </button>
      </div>

      <button
        type="button"
        className="link"
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        {showAdvanced ? "▾" : "▸"} Advanced: router commands
      </button>
      {showAdvanced && (
        <div className="advanced">
          <p className="muted small">
            Override only if your firmware differs. Defaults work for stock
            Asuswrt and Merlin.
          </p>
          {ADVANCED.map(([key, label]) => (
            <label key={key} className="field">
              <span>{label}</span>
              <input
                className="mono"
                value={form[key] ?? ""}
                onChange={(e) => set(key, e.target.value)}
              />
            </label>
          ))}
        </div>
      )}

      <div className="actions">
        <button type="submit">Save</button>
        <button type="button" className="secondary" onClick={runTest}>
          Test connection
        </button>
        {saved && <span className="ok">Saved ✓</span>}
      </div>

      {test?.status === "testing" && <div className="banner">Testing…</div>}

      {test?.results && (
        <div className="test-results">
          {test.results.map((r) => (
            <div key={r.name} className={`banner ${r.ok ? "success" : "error"}`}>
              <strong>{r.name}</strong>{" — "}
              {r.ok
                ? `connected (interfaces: ${(r.interfaces || []).join(", ") || "none found"})`
                : r.error}
            </div>
          ))}
        </div>
      )}
    </form>
  );
}
