import React, { useState } from "react";
import { api } from "../api.js";

// Triggers an immediate backend poll cycle (SSH the router/APs now rather than
// waiting for the next interval). Calls onDone after the refresh completes.
export default function RefreshButton({ onDone }) {
  const [busy, setBusy] = useState(false);

  async function refresh() {
    if (busy) return;
    setBusy(true);
    try {
      await api.refresh();
      if (onDone) await onDone();
    } catch {
      /* surfaced via the dashboard status banner */
    } finally {
      setBusy(false);
    }
  }

  return (
    <button className="refresh" onClick={refresh} disabled={busy}>
      <span className={busy ? "spin" : ""}>↻</span> {busy ? "Refreshing…" : "Refresh"}
    </button>
  );
}
