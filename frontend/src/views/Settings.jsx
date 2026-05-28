import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const FIELDS = [
  ["router_host", "Router host / IP", "text"],
  ["router_port", "SSH port", "number"],
  ["router_user", "SSH username", "text"],
  ["router_password", "SSH password", "password"],
  ["router_key_path", "SSH key path (optional, overrides password)", "text"],
  ["poll_interval", "Poll interval (seconds)", "number"],
  ["grace_minutes", "Away grace window (minutes)", "number"],
];

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

      {test && (
        <div className={`banner ${test.ok ? "success" : test.status ? "" : "error"}`}>
          {test.status === "testing" && "Testing…"}
          {test.ok && `Connected. Wireless interfaces: ${test.interfaces.join(", ") || "none found"}`}
          {test.ok === false && `Failed: ${test.error}`}
        </div>
      )}
    </form>
  );
}
