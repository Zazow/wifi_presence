// Thin REST client + live WebSocket helper.
import type {
  ConnStatus,
  Device,
  DevicePatch,
  Person,
  PresenceState,
  Settings,
  TestResults,
  WhoAmI,
} from "./types";

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const opts: RequestInit = { method, headers: {} };
  if (body !== undefined) {
    opts.headers = { "Content-Type": "application/json" };
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  if (res.status === 204) return null as T;
  return res.json() as Promise<T>;
}

export const api = {
  getState: () => req<PresenceState>("GET", "/api/state"),
  listDevices: () => req<Device[]>("GET", "/api/devices"),
  patchDevice: (mac: string, patch: DevicePatch) =>
    req<Device>("PATCH", `/api/devices/${encodeURIComponent(mac)}`, patch),
  listPeople: () => req<Person[]>("GET", "/api/people"),
  createPerson: (name: string) => req<Person>("POST", "/api/people", { name }),
  renamePerson: (id: number, name: string) =>
    req<Person>("PATCH", `/api/people/${id}`, { name }),
  deletePerson: (id: number) => req<void>("DELETE", `/api/people/${id}`),
  getSettings: () => req<Settings>("GET", "/api/settings"),
  putSettings: (s: Partial<Settings>) => req<Settings>("PUT", "/api/settings", s),
  testRouter: () => req<TestResults>("POST", "/api/router/test"),
  refresh: () => req<PresenceState>("POST", "/api/refresh"),
  whoami: () => req<WhoAmI>("GET", "/api/whoami"),
};

// Subscribe to live state pushes. Auto-reconnects. Returns a cleanup fn.
export function subscribeState(
  onState: (s: PresenceState) => void,
  onStatusChange: (status: ConnStatus) => void
): () => void {
  let ws: WebSocket | undefined;
  let closed = false;
  let retry: ReturnType<typeof setTimeout> | undefined;

  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/api/ws`);
    ws.onopen = () => onStatusChange("connected");
    ws.onmessage = (e: MessageEvent) => {
      try {
        onState(JSON.parse(e.data as string));
      } catch {
        /* ignore malformed frame */
      }
    };
    ws.onclose = () => {
      if (closed) return;
      onStatusChange("disconnected");
      retry = setTimeout(connect, 3000);
    };
    ws.onerror = () => ws?.close();
  }
  connect();

  return () => {
    closed = true;
    if (retry) clearTimeout(retry);
    ws?.close();
  };
}
