import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { deviceName } from "../util.js";

// "Register this device": detects the device the user is browsing from (by
// matching their IP to a known device) and assigns it to a person — so a family
// member can just open the page on their phone and tap to register. If the
// device can't be auto-detected (e.g. opened on the server itself, IPv6-only,
// or a stale ARP entry), fall back to picking it from the device list.
export default function RegisterDeviceModal({ onClose, onDone }) {
  const [loading, setLoading] = useState(true);
  const [info, setInfo] = useState(null); // { ip, device }
  const [devices, setDevices] = useState([]);
  const [people, setPeople] = useState([]);
  const [manualMac, setManualMac] = useState("");
  const [pickManually, setPickManually] = useState(false);
  const [sel, setSel] = useState("");
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  async function detect() {
    setLoading(true);
    const [w, d, p] = await Promise.all([
      api.whoami(),
      api.listDevices(),
      api.listPeople(),
    ]);
    setInfo(w);
    setDevices(d);
    setPeople(p);
    setLoading(false);
  }

  useEffect(() => {
    detect();
  }, []);

  const autoDev = info?.device;
  // Choices for the manual picker: visible devices, present ones first.
  const pickable = useMemo(
    () =>
      devices
        .filter((d) => !d.ignored)
        .sort(
          (a, b) =>
            (b.is_present ? 1 : 0) - (a.is_present ? 1 : 0) ||
            (b.last_seen || 0) - (a.last_seen || 0)
        ),
    [devices]
  );
  const usingManual = pickManually || !autoDev;
  const target = usingManual ? devices.find((d) => d.mac === manualMac) : autoDev;

  async function register() {
    if (!target) return;
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
      await api.patchDevice(target.mac, { person_id: Number(pid) });
      setDone(true);
      if (onDone) await onDone();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Register a device</h2>

        {loading && <div className="muted">Detecting this device…</div>}

        {!loading && !done && (
          <>
            {autoDev && !pickManually ? (
              <div className="detected">
                <div className="detected-name">{deviceName(autoDev)}</div>
                <div className="muted mono small">
                  {autoDev.mac}
                  {autoDev.vendor ? ` · ${autoDev.vendor}` : ""}
                  {autoDev.ip ? ` · ${autoDev.ip}` : ""}
                </div>
                {autoDev.person_id != null && (
                  <div className="muted small">Already assigned — registering will reassign it.</div>
                )}
                <button
                  type="button"
                  className="link"
                  onClick={() => setPickManually(true)}
                >
                  Not this device? Choose manually
                </button>
              </div>
            ) : (
              <>
                {!autoDev && (
                  <div className="banner">
                    Couldn't auto-detect your device
                    {info?.ip ? ` (request came from ${info.ip})` : ""}. For
                    auto-detect, open this page on the phone over home Wi-Fi.
                    Otherwise, pick the device below.
                  </div>
                )}
                <label className="field">
                  <span>Choose the device</span>
                  <select value={manualMac} onChange={(e) => setManualMac(e.target.value)}>
                    <option value="">— choose a device —</option>
                    {pickable.map((d) => (
                      <option key={d.mac} value={d.mac}>
                        {deviceName(d)}
                        {d.ip ? ` · ${d.ip}` : ""}
                        {d.is_present ? " · present" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                {autoDev && (
                  <button
                    type="button"
                    className="link"
                    onClick={() => {
                      setPickManually(false);
                      setManualMac("");
                    }}
                  >
                    ← Use the auto-detected device
                  </button>
                )}
              </>
            )}

            {target && (
              <>
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
              </>
            )}

            <div className="actions">
              <button
                onClick={register}
                disabled={saving || !target || (!sel && !newName.trim())}
              >
                {saving ? "Saving…" : "Register"}
              </button>
              <button type="button" className="secondary" onClick={onClose}>
                Cancel
              </button>
            </div>
          </>
        )}

        {done && (
          <>
            <div className="banner success">
              Registered <strong>{deviceName(target)}</strong> ✓
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
