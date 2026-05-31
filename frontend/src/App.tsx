import { useEffect, useState } from "react";
import { subscribeState } from "./api";
import type { ConnStatus, PresenceState } from "./types";
import Dashboard from "./views/Dashboard";
import Devices from "./views/Devices";
import People from "./views/People";
import Settings from "./views/Settings";

type Tab = "dashboard" | "devices" | "people" | "settings";

const TABS: [Tab, string][] = [
  ["dashboard", "Dashboard"],
  ["devices", "Devices"],
  ["people", "People"],
  ["settings", "Settings"],
];

export default function App() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [state, setState] = useState<PresenceState | null>(null);
  const [conn, setConn] = useState<ConnStatus>("connecting");

  useEffect(() => subscribeState(setState, setConn), []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-dot" />
          <span className="brand-name">WiFi Presence</span>
        </div>

        <nav className="tabs">
          {TABS.map(([id, label]) => (
            <button
              key={id}
              className={tab === id ? "tab active" : "tab"}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </nav>

        <div className={`conn conn-${conn}`} title={`WebSocket ${conn}`}>
          <span className="conn-dot" />
          {conn === "connected" ? "Live" : conn === "connecting" ? "…" : "Offline"}
        </div>
      </header>

      <main className="content">
        {tab === "dashboard" && <Dashboard state={state} />}
        {tab === "devices" && <Devices />}
        {tab === "people" && <People />}
        {tab === "settings" && <Settings />}
      </main>
    </div>
  );
}
