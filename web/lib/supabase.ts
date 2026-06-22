import { createClient } from "@supabase/supabase-js";

export type Device = {
  mac: string;
  hostname: string | null;
  custom_name: string | null;
  vendor: string | null;
  is_randomized: boolean;
  is_online: boolean;
  last_ip: string | null;
  interface: string | null;
  first_seen: string;
  last_seen: string;
  hidden: boolean;
  notes: string | null;
  updated_at: string;
};

export type DeviceEvent = {
  id: number;
  mac: string;
  type: "online" | "offline";
  ts: string;
  ip: string | null;
  hostname: string | null;
};

export type Poll = {
  id: number;
  ts: string;
  active_count: number | null;
  total_count: number | null;
  ok: boolean;
  error: string | null;
};

export type Session = {
  mac: string;
  started_at: string;
  ended_at: string | null;
  duration: string; // postgres interval as string
};

/** Server-only admin client (service_role key). Never import from a Client Component. */
export function supabaseAdmin() {
  // .trim() guards against trailing newlines/whitespace in env vars.
  const url = process.env.SUPABASE_URL?.trim();
  const key = process.env.SUPABASE_SERVICE_KEY?.trim();
  if (!url || !key) {
    throw new Error("SUPABASE_URL / SUPABASE_SERVICE_KEY env vars are not set");
  }
  return createClient(url, key, { auth: { persistSession: false } });
}

export function displayName(d: Device): string {
  return d.custom_name || d.hostname || d.mac;
}
