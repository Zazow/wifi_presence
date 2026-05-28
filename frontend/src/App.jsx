import React, { useEffect, useState } from "react";
import { subscribeState } from "./api.js";
import Dashboard from "./views/Dashboard.jsx";
import Devices from "./views/Devices.jsx";
import People from "./views/People.jsx";
import Settings from "./views/Settings.jsx";

const TABS = [
  ["dashboard", "Dashboard"],
  ["devices", "Devices"],
  ["people", "People"],
  ["settings", "Settings"],
];

export default function App() {
  const [tab, setTab] = useState("dashboard");
  const [state, setState] = useState(null);
  const [conn, setConn] = useState("connecting");

  useEffect(() => subscribeState(setState, setConn), []);

  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="logo">●</span> WiFi Presence
        </div>
        <nav>
          {TABS.map(([id, label]) => (
            <button
              key={id}
              className={tab === id ? "active" : ""}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </nav>
        <div className={`conn conn-${conn}`} title={`WebSocket ${conn}`}>
          {conn === "connected" ? "live" : conn}
        </div>
      </header>

      <main>
        {tab === "dashboard" && <Dashboard state={state} />}
        {tab === "devices" && <Devices />}
        {tab === "people" && <People />}
        {tab === "settings" && <Settings />}
      </main>
    </div>
  );
}
