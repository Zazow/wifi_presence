import React, { useState } from "react";
import { api } from "../api.js";
import { timeAgo, deviceName } from "../util.js";
import RefreshButton from "../components/RefreshButton.jsx";
import RegisterDeviceModal from "../components/RegisterDeviceModal.jsx";

export default function Dashboard({ state }) {
  // Open the register flow automatically when arriving via the QR link.
  const [showRegister, setShowRegister] = useState(
    () => new URLSearchParams(location.search).get("register") === "1"
  );
  if (!state) return <div className="loading">Connecting…</div>;

  const people = state.people || [];
  const home = people.filter((p) => p.home);
  const away = people.filter((p) => !p.home);
  const unassigned = state.unassigned_present || [];
  const status = state.status || {};

  return (
    <div className="dashboard">
      <div className="summary">
        <div className="summary-num">{home.length}</div>
        <div className="summary-label">home</div>
        <div className="summary-sep" />
        <div className="summary-num muted">{away.length}</div>
        <div className="summary-label">away</div>
        <div className="summary-spacer" />
        <button className="register-btn" onClick={() => setShowRegister(true)}>
          + Register this device
        </button>
        <RefreshButton />
      </div>

      {showRegister && (
        <RegisterDeviceModal
          onClose={() => setShowRegister(false)}
          onDone={() => api.refresh()}
        />
      )}

      {status.last_error && (
        <div className="banner error">
          Router unreachable: {status.last_error}. Showing last known presence.
        </div>
      )}

      {people.length === 0 && (
        <div className="empty">
          No people yet. Go to <strong>Devices</strong> to assign phones to
          <strong> People</strong>.
        </div>
      )}

      <section>
        <h2>Home</h2>
        <div className="cards">
          {home.map((p) => (
            <PersonCard key={p.id} person={p} home />
          ))}
          {home.length === 0 && <div className="muted">Nobody home.</div>}
        </div>
      </section>

      <section>
        <h2>Away</h2>
        <div className="cards">
          {away.map((p) => (
            <PersonCard key={p.id} person={p} />
          ))}
          {away.length === 0 && people.length > 0 && (
            <div className="muted">Everyone's home.</div>
          )}
        </div>
      </section>

      {unassigned.length > 0 && (
        <section>
          <h2>
            Unassigned devices present <span className="pill">{unassigned.length}</span>
          </h2>
          <div className="muted small">
            Present devices not yet linked to a person. Assign or ignore them in
            the Devices tab.
          </div>
          <div className="chips">
            {unassigned.map((d) => (
              <span className="chip" key={d.mac} title={d.mac}>
                {deviceName(d)}
                {d.ap ? ` · ${d.ap}` : d.vendor ? ` · ${d.vendor}` : ""}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function PersonCard({ person, home }) {
  const activeDevices = (person.devices || []).filter((d) => d.active);
  return (
    <div className={`card person ${home ? "home" : "away"}`}>
      <div className="person-top">
        <span className={`dot ${home ? "green" : "grey"}`} />
        <span className="person-name">{person.name}</span>
      </div>
      <div className="person-sub">
        {home ? (
          <span>
            {activeDevices.length} device{activeDevices.length === 1 ? "" : "s"} present
          </span>
        ) : (
          <span>last seen {timeAgo(person.last_seen)}</span>
        )}
      </div>
      <div className="person-devices">
        {(person.devices || []).map((d) => (
          <span
            key={d.mac}
            className={`mini ${d.active ? "on" : "off"}`}
            title={d.ap ? `on ${d.ap}` : ""}
          >
            {deviceName(d)}
            {d.active && d.ap ? ` · ${d.ap}` : ""}
          </span>
        ))}
        {(person.devices || []).length === 0 && (
          <span className="muted small">no devices assigned</span>
        )}
      </div>
    </div>
  );
}
