import { useState } from "react";
import { api } from "../api";
import { avatarHue, deviceName, initials, timeAgo } from "../util";
import type { PersonState, PresenceState } from "../types";
import RefreshButton from "../components/RefreshButton";
import RegisterDeviceModal from "../components/RegisterDeviceModal";

export default function Dashboard({ state }: { state: PresenceState | null }) {
  // Open the register flow automatically when arriving via the QR link.
  const [showRegister, setShowRegister] = useState(
    () => new URLSearchParams(location.search).get("register") === "1"
  );

  if (!state) return <div className="loading">Connecting…</div>;

  const people = state.people ?? [];
  const home = people.filter((p) => p.home);
  const away = people.filter((p) => !p.home);
  const unassigned = state.unassigned_present ?? [];
  const status = state.status;

  return (
    <div className="dashboard">
      <section className="hero">
        <div className="hero-stats">
          <div className="stat">
            <div className="stat-num accent">{home.length}</div>
            <div className="stat-label">home</div>
          </div>
          <div className="stat-divider" />
          <div className="stat">
            <div className="stat-num muted">{away.length}</div>
            <div className="stat-label">away</div>
          </div>
        </div>
        <div className="hero-actions">
          <button className="btn btn-primary" onClick={() => setShowRegister(true)}>
            + Register this device
          </button>
          <RefreshButton />
        </div>
      </section>

      {showRegister && (
        <RegisterDeviceModal
          onClose={() => setShowRegister(false)}
          onDone={async () => {
            await api.refresh();
          }}
        />
      )}

      {status?.last_error && (
        <div className="banner error">
          Router unreachable: {status.last_error}. Showing last known presence.
        </div>
      )}

      {people.length === 0 && (
        <div className="empty">
          No people yet. Tap <strong>Register this device</strong>, or open
          <strong> Devices</strong> to assign phones to people.
        </div>
      )}

      {home.length > 0 && (
        <section className="group">
          <h2 className="group-title">
            Home <span className="count">{home.length}</span>
          </h2>
          <div className="cards">
            {home.map((p) => (
              <PersonCard key={p.id} person={p} home />
            ))}
          </div>
        </section>
      )}

      {away.length > 0 && (
        <section className="group">
          <h2 className="group-title">
            Away <span className="count">{away.length}</span>
          </h2>
          <div className="cards">
            {away.map((p) => (
              <PersonCard key={p.id} person={p} />
            ))}
          </div>
        </section>
      )}

      {unassigned.length > 0 && (
        <section className="group">
          <h2 className="group-title">
            Unassigned nearby <span className="count">{unassigned.length}</span>
          </h2>
          <p className="muted small">
            Present devices not yet linked to a person. Assign or ignore them in Devices.
          </p>
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

function PersonCard({ person, home = false }: { person: PersonState; home?: boolean }) {
  const devices = person.devices ?? [];
  const activeCount = devices.filter((d) => d.active).length;
  const hue = avatarHue(person.name);

  return (
    <div className={`person-card ${home ? "is-home" : "is-away"}`}>
      <div className="person-head">
        <span
          className="avatar"
          style={{
            background: `hsl(${hue} 55% 22%)`,
            color: `hsl(${hue} 80% 72%)`,
            borderColor: `hsl(${hue} 60% 40% / 0.5)`,
          }}
        >
          {initials(person.name)}
        </span>
        <div className="person-meta">
          <div className="person-name">{person.name}</div>
          <div className="person-status">
            <span className={`status-dot ${home ? "on" : "off"}`} />
            {home
              ? `${activeCount} device${activeCount === 1 ? "" : "s"} present`
              : `last seen ${timeAgo(person.last_seen)}`}
          </div>
        </div>
      </div>
      {devices.length > 0 && (
        <div className="person-devices">
          {devices.map((d) => (
            <span
              key={d.mac}
              className={`mini ${d.active ? "on" : "off"}`}
              title={d.ap ? `on ${d.ap}` : d.mac}
            >
              {deviceName(d)}
              {d.active && d.ap ? ` · ${d.ap}` : ""}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
