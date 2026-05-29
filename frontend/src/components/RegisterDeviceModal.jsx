import React, { useEffect, useState } from "react";
import qrcode from "qrcode-generator";
import { api } from "../api.js";
import { deviceName } from "../util.js";

const LOOPBACK = ["localhost", "127.0.0.1", "::1", "[::1]"];

// URL to open on the phone so it lands straight on the register flow.
function phoneUrl(serverIp) {
  const onLoopback = LOOPBACK.includes(location.hostname);
  // When viewing on the server itself, swap in the server's LAN IP so the QR
  // is reachable from a phone; otherwise the current origin already works.
  const host = onLoopback && serverIp ? `${serverIp}:${location.port}` : location.host;
  return `${location.protocol}//${host}/?register=1`;
}

function qrDataUrl(text) {
  const qr = qrcode(0, "M");
  qr.addData(text);
  qr.make();
  return qr.createDataURL(5, 12);
}

// "Register this device": the phone identifies itself by its IP, so a family
// member just opens the page on their phone and taps to assign it — no list,
// no MAC hunting. When opened somewhere that ISN'T the phone (e.g. a desktop),
// we show a QR code to open the flow on the phone instead.
export default function RegisterDeviceModal({ onClose, onDone }) {
  const [loading, setLoading] = useState(true);
  const [info, setInfo] = useState(null); // { ip, device, server_ip }
  const [people, setPeople] = useState([]);
  const [sel, setSel] = useState("");
  const [newName, setNewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    (async () => {
      const [w, p] = await Promise.all([api.whoami(), api.listPeople()]);
      setInfo(w);
      setPeople(p);
      setLoading(false);
    })();
  }, []);

  const dev = info?.device;

  async function register() {
    if (!dev) return;
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
      await api.patchDevice(dev.mac, { person_id: Number(pid) });
      setDone(true);
      if (onDone) await onDone();
    } finally {
      setSaving(false);
    }
  }

  const url = info ? phoneUrl(info.server_ip) : "";

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Register this device</h2>

        {loading && <div className="muted">Detecting this device…</div>}

        {/* Not the phone: show a QR to open the flow on the phone itself. */}
        {!loading && !dev && !done && (
          <>
            <p className="muted small">
              This works from the device you want to register. Scan this with the
              phone (on home Wi-Fi) to open the page there and register it in one tap:
            </p>
            <div className="qr-wrap">
              <img src={qrDataUrl(url)} alt="QR code to open on your phone" />
            </div>
            <div className="muted small center mono qr-url">{url}</div>
            <div className="actions">
              <button type="button" className="secondary" onClick={onClose}>Close</button>
            </div>
          </>
        )}

        {/* On the phone: it identified itself — just pick the person. */}
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
