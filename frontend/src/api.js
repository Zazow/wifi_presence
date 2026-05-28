// Thin REST client + live WebSocket helper.

async function req(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  getState: () => req("GET", "/api/state"),
  listDevices: () => req("GET", "/api/devices"),
  patchDevice: (mac, patch) => req("PATCH", `/api/devices/${encodeURIComponent(mac)}`, patch),
  listPeople: () => req("GET", "/api/people"),
  createPerson: (name) => req("POST", "/api/people", { name }),
  renamePerson: (id, name) => req("PATCH", `/api/people/${id}`, { name }),
  deletePerson: (id) => req("DELETE", `/api/people/${id}`),
  getSettings: () => req("GET", "/api/settings"),
  putSettings: (s) => req("PUT", "/api/settings", s),
  testRouter: () => req("POST", "/api/router/test"),
};

// Subscribe to live state pushes. Auto-reconnects. Returns a cleanup fn.
export function subscribeState(onState, onStatusChange) {
  let ws;
  let closed = false;
  let retry;

  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/api/ws`);
    ws.onopen = () => onStatusChange && onStatusChange("connected");
    ws.onmessage = (e) => {
      try {
        onState(JSON.parse(e.data));
      } catch {
        /* ignore malformed frame */
      }
    };
    ws.onclose = () => {
      if (closed) return;
      onStatusChange && onStatusChange("disconnected");
      retry = setTimeout(connect, 3000);
    };
    ws.onerror = () => ws.close();
  }
  connect();

  return () => {
    closed = true;
    clearTimeout(retry);
    if (ws) ws.close();
  };
}
