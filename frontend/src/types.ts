// Shared API types (mirror the FastAPI backend's JSON shapes).

export interface Device {
  mac: string;
  hostname: string | null;
  ip: string | null;
  vendor: string | null;
  interface: string | null;
  ap: string | null;
  label: string | null;
  person_id: number | null;
  ignored: number;
  first_seen: number | null;
  last_seen: number | null;
  is_present: number;
  active?: boolean; // added by the presence engine in state payloads
}

export interface Person {
  id: number;
  name: string;
  created_at?: number;
}

export interface PersonState {
  id: number;
  name: string;
  home: boolean;
  last_seen: number | null;
  devices: Device[];
}

export interface PresenceState {
  now: number;
  grace_minutes: number;
  people: PersonState[];
  unassigned_present: Device[];
  status?: { last_poll: number | null; last_error: string | null };
}

export interface AccessPoint {
  name: string;
  host: string;
  port: number;
  user: string;
  password: string;
  key_path: string;
}

export interface Settings {
  router_name: string;
  router_host: string;
  router_port: number;
  router_user: string;
  router_password: string;
  router_key_path: string;
  poll_interval: number;
  grace_minutes: number;
  cmd_ifnames: string;
  cmd_assoclist: string;
  cmd_neigh: string;
  cmd_leases: string;
  cmd_fdb: string;
  access_points: AccessPoint[];
}

export interface WhoAmI {
  ip: string;
  device: Device | null;
  server_ip: string | null;
}

export interface TestTarget {
  name: string;
  ok: boolean;
  stage?: string;
  interfaces?: string[];
  error?: string;
}

export interface TestResults {
  results: TestTarget[];
}

export type ConnStatus = "connecting" | "connected" | "disconnected";

export interface DevicePatch {
  label?: string;
  person_id?: number | null;
  ignored?: boolean;
  unassign?: boolean;
}
