import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { deviceName } from "../util.js";

// "Register this device": detects the device the user is browsing from (by
// matching their IP to a known device) and assigns it to a person — so a family
// member can just open the page on their phone and tap to register.
export default function RegisterDeviceModal({ onClose, onDone }) {
  const [loading, setLoading] = useState(true);
  const [info, setInfo] = useState(null); // { ip, device }
  const [people, setPeople] = useState([]);
  const [sel, setSel] = useState("");
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  async function detect() {
    setLoading(true);
    const [w, p] = await Promise.all([api.whoami(), api.listPeople()]);
    setInfo(w);
    setPeople(p);
    setLoading(false);
  }

  useEffect(() => {
    detect();
  }, []);

  async function register() {
    if (!info?.device) return;
    setSaving(true);
    try {
      let pid = sel;
      if (newName.trim()) {
        const np = await api.createPerson(newName.trim());
        pid = np.id;
      }
      if (!pid) {
        setSaving(false);
        return;
      }
      await api.patchDevice(info.device.mac, { person_id: Number(pid) });
      setDone(true);
      if (onDone) await onDone();
    } finally {
      setSaving(false);
    }
  }

  const dev = info?.device;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Register this device</h2>

        {loading && <div className="muted">Detecting this device…</div>}

        {!loading && !dev && (
          <>
            <div className="banner error">
              Couldn't identify this device from {info?.ip || "your connection"}.
              Open this page <strong>on the phone you want to register</strong>,
              connected to home Wi-Fi (not mobile data or a VPN), then try again.
            </div>
            <div className="actions">
              <button onClick={detect}>Try again</button>
              <button className="secondary" onClick={onClose}>Cancel</button>
            </div>
          </>
        )}

        {!loading && dev && !done && (
          <>
            <div className="detected">
              <div className="detected-name">{deviceName(dev)}</div>
              <div className="muted mono small">
                {dev.mac}
                {dev.vendor ? ` · ${dev.vendor}` : ""}
                {dev.ip ? ` · ${dev.ip}` : ""}
              </div>
              {dev.person_id != null && (
                <div className="muted small">Already assigned — registering will reassign it.</div>
              )}
            </div>

            <label className="field">
              <span>Assign to an existing person</span>
              <select
                value={sel}
                onChange={(e) => {
                  setSel(e.target.value);
                  setNewName("");
                }}
              >
                <option value="">— choose —</option>
                {people.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </label>

            <div className="muted small center or-sep">or</div>

            <label className="field">
              <span>Create a new person</span>
              <input
                value={newName}
                placeholder="e.g. Brother"
                onChange={(e) => {
                  setNewName(e.target.value);
                  setSel("");
                }}
              />
            </label>

            <div className="actions">
              <button onClick={register} disabled={saving || (!sel && !newName.trim())}>
                {saving ? "Saving…" : "Register"}
              </button>
              <button type="button" className="secondary" onClick={onClose}>Cancel</button>
            </div>
          </>
        )}

        {done && (
          <>
            <div className="banner success">
              Registered <strong>{deviceName(dev)}</strong> ✓
            </div>
            <div className="actions">
              <button onClick={onClose}>Done</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
