import { useEffect, useState } from "react";
import { api } from "../api";
import type { AccessPoint, Settings as SettingsType, TestResults, TestTarget } from "../types";

type FieldType = "text" | "number" | "password";
type FieldKey =
  | "router_name"
  | "router_host"
  | "router_port"
  | "router_user"
  | "router_password"
  | "router_key_path"
  | "poll_interval"
  | "grace_seconds";
type CmdKey = "cmd_ifnames" | "cmd_assoclist" | "cmd_neigh" | "cmd_leases" | "cmd_fdb";
type NotifyKey = "notify_ntfy_url" | "notify_webhook_url";

const NOTIFY_FIELDS: [NotifyKey, string][] = [
  ["notify_ntfy_url", "ntfy topic URL (e.g. https://ntfy.sh/my-house)"],
  ["notify_webhook_url", "Webhook URL (JSON POST on arrive/leave)"],
];

const FIELDS: [FieldKey, string, FieldType][] = [
  ["router_name", "Main router name (shown as its AP)", "text"],
  ["router_host", "Router host / IP", "text"],
  ["router_port", "SSH port", "number"],
  ["router_user", "SSH username", "text"],
  ["router_password", "SSH password", "password"],
  ["router_key_path", "SSH key path (optional, overrides password)", "text"],
  ["poll_interval", "Poll interval — seconds between router checks", "number"],
  ["grace_seconds", "Away grace — seconds unseen before 'away'", "number"],
];

const AP_FIELDS: [keyof AccessPoint, string, FieldType][] = [
  ["name", "Name (e.g. Upstairs)", "text"],
  ["host", "Host / IP", "text"],
  ["port", "Port", "number"],
  ["user", "User", "text"],
  ["password", "Password", "password"],
];

const BLANK_AP: AccessPoint = { name: "", host: "", port: 22, user: "", password: "", key_path: "" };

const ADVANCED: [CmdKey, string][] = [
  ["cmd_ifnames", "Wireless interfaces command"],
  ["cmd_assoclist", "Assoc list command ({iface} placeholder)"],
  ["cmd_neigh", "Neighbour/ARP command"],
  ["cmd_leases", "DHCP leases command"],
  ["cmd_fdb", "Bridge table command (finds devices behind APs; blank = off)"],
];

type TestState = { status: "testing" } | TestResults | null;

export default function Settings() {
  const [form, setForm] = useState<SettingsType | null>(null);
  const [saved, setSaved] = useState(false);
  const [test, setTest] = useState<TestState>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    api.getSettings().then(setForm);
  }, []);

  if (!form) return <div className="loading">Loading settings…</div>;

  const set = (k: keyof SettingsType, v: unknown) => {
    setForm({ ...form, [k]: v } as SettingsType);
    setSaved(false);
  };

  const aps = form.access_points ?? [];
  const setAps = (next: AccessPoint[]) => set("access_points", next);
  const addAp = () => setAps([...aps, { ...BLANK_AP }]);
  const updateAp = (i: number, key: keyof AccessPoint, val: string | number) =>
    setAps(aps.map((ap, j) => (j === i ? ({ ...ap, [key]: val } as AccessPoint) : ap)));
  const removeAp = (i: number) => setAps(aps.filter((_, j) => j !== i));

  function payloadFromForm(): Partial<SettingsType> {
    const payload: Partial<SettingsType> = { ...(form as SettingsType) };
    // Don't send back the redaction placeholder.
    if (payload.router_password === "********") delete payload.router_password;
    return payload;
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const updated = await api.putSettings(payloadFromForm());
    setForm(updated);
    setSaved(true);
  }

  async function runTest() {
    setTest({ status: "testing" });
    await api.putSettings(payloadFromForm()); // persist current values first
    setTest(await api.testRouter());
  }

  return (
    <form className="settings" onSubmit={save}>
      <div className="card form-card">
        <p className="muted small">Settings are saved to the database and persist across restarts.</p>
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
        <p className="muted small">
          Updates (disconnects, AP changes) appear within one poll interval, so
          lower it for snappier results — e.g. 5s. The grace window is the floor
          before someone flips to "away"; it's automatically kept at least as
          large as the poll interval to avoid false "away" flicker.
        </p>
      </div>

      <div className="card form-card ap-section">
        <h2 className="section-title">Access points</h2>
        <p className="muted small">
          Add your bridge-mode / AP-mode access points so devices show the AP
          they're on. Each is polled over SSH; blank user/password fall back to
          the main router's. Devices on an AP that isn't listed show as "behind AP".
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
            <button type="button" className="btn-link danger" onClick={() => removeAp(i)}>
              remove
            </button>
          </div>
        ))}
        <button type="button" className="btn-link" onClick={addAp}>
          + Add access point
        </button>
      </div>

      <div className="card form-card">
        <h2 className="section-title">Notifications</h2>
        <p className="muted small">
          Optional — get a push when someone arrives or leaves. Fill either or
          both; leave blank to disable.
        </p>
        {NOTIFY_FIELDS.map(([key, label]) => (
          <label key={key} className="field">
            <span>{label}</span>
            <input
              value={form[key] ?? ""}
              placeholder="https://…"
              onChange={(e) => set(key, e.target.value)}
            />
          </label>
        ))}
      </div>

      <button
        type="button"
        className="btn-link"
        onClick={() => setShowAdvanced(!showAdvanced)}
      >
        {showAdvanced ? "▾" : "▸"} Advanced: router commands
      </button>
      {showAdvanced && (
        <div className="card form-card">
          <p className="muted small">
            Override only if your firmware differs. Defaults work for stock Asuswrt and Merlin.
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
        <button type="submit" className="btn btn-primary">Save</button>
        <button type="button" className="btn btn-ghost" onClick={runTest}>
          Test connection
        </button>
        {saved && <span className="ok">Saved ✓</span>}
      </div>

      {test && "status" in test && <div className="banner">Testing…</div>}

      {test && "results" in test && (
        <div className="test-results">
          {test.results.map((r: TestTarget) => (
            <div key={r.name} className={`banner ${r.ok ? "success" : "error"}`}>
              <strong>{r.name}</strong>
              {" — "}
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
