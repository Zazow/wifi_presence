import type { Device } from "./types";

export function timeAgo(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return "never";
  const secs = Math.max(0, Math.floor(Date.now() / 1000 - epochSeconds));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function deviceName(d: Device): string {
  return d.label || d.hostname || d.mac;
}

// Compact "how long since" duration, e.g. "3h 12m", "5m", "just now".
export function durationSince(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return "—";
  const secs = Math.max(0, Math.floor(Date.now() / 1000 - epochSeconds));
  if (secs < 60) return "just now";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ${mins % 60}m`;
  const days = Math.floor(hrs / 24);
  return `${days}d ${hrs % 24}h`;
}

// Absolute local time, e.g. "14:03". For tooltips.
export function clockTime(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return "";
  return new Date(epochSeconds * 1000).toLocaleString();
}

// Stable initials + colour for a person, used for avatars.
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const AVATAR_HUES = [262, 200, 152, 28, 340, 12, 96, 220];

export function avatarHue(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return AVATAR_HUES[h % AVATAR_HUES.length];
}

// Tinted avatar colours tuned for a light background.
export function avatarStyle(name: string): {
  background: string;
  color: string;
  borderColor: string;
} {
  const h = avatarHue(name);
  return {
    background: `hsl(${h} 72% 94%)`,
    color: `hsl(${h} 45% 34%)`,
    borderColor: `hsl(${h} 52% 85%)`,
  };
}
