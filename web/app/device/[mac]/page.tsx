import { connection } from "next/server";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  supabaseAdmin,
  displayName,
  type Device,
  type DeviceEvent,
  type Session,
} from "@/lib/supabase";
import { fmtAgo, fmtDuration, fmtSince, fmtTime } from "@/lib/format";
import { renameDevice, saveNotes, setHidden } from "@/app/actions";
import AutoRefresh from "@/components/AutoRefresh";

function sessionMs(s: Session): number {
  const end = s.ended_at ? new Date(s.ended_at).getTime() : Date.now();
  return end - new Date(s.started_at).getTime();
}

export default async function DevicePage({
  params,
}: {
  params: Promise<{ mac: string }>;
}) {
  await connection();
  const { mac: macParam } = await params;
  const mac = decodeURIComponent(macParam);

  const sb = supabaseAdmin();
  const [deviceRes, eventsRes, sessionsRes] = await Promise.all([
    sb.from("devices").select("*").eq("mac", mac).maybeSingle(),
    sb.from("events").select("*").eq("mac", mac).order("ts", { ascending: false }).limit(100),
    sb.from("device_sessions").select("*").eq("mac", mac).order("started_at", { ascending: false }).limit(50),
  ]);

  const device = deviceRes.data as Device | null;
  if (!device) notFound();

  const events = (eventsRes.data ?? []) as DeviceEvent[];
  const sessions = (sessionsRes.data ?? []) as Session[];

  const weekAgo = Date.now() - 7 * 24 * 3600 * 1000;
  const uptime7d = sessions
    .filter((s) => new Date(s.ended_at ?? new Date()).getTime() > weekAgo)
    .reduce((sum, s) => sum + sessionMs(s), 0);

  return (
    <main className="mx-auto max-w-3xl p-4 sm:p-8">
      <AutoRefresh seconds={30} />

      <Link href="/" className="text-sm text-neutral-400 hover:text-neutral-200">
        ← all devices
      </Link>

      <header className="mt-3 flex items-center gap-3">
        <span
          className={`h-3 w-3 rounded-full ${device.is_online ? "bg-emerald-400" : "bg-neutral-600"}`}
        />
        <h1 className="text-2xl font-semibold tracking-tight">{displayName(device)}</h1>
        <span className="text-sm text-neutral-400">
          {device.is_online ? `online · ${fmtSince(device.last_seen)}` : `seen ${fmtAgo(device.last_seen)}`}
        </span>
      </header>

      {/* meta */}
      <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 rounded-xl border border-neutral-800 p-4 text-sm sm:grid-cols-3">
        <Meta label="MAC" value={device.mac} mono />
        <Meta label="IP" value={device.last_ip ?? "—"} mono />
        <Meta label="Link" value={device.interface ?? "—"} />
        <Meta label="Hostname" value={device.hostname ?? "—"} />
        <Meta label="First seen" value={fmtTime(device.first_seen)} />
        <Meta label="Uptime (7d)" value={fmtDuration(uptime7d)} />
      </dl>

      {device.is_randomized && (
        <p className="mt-3 rounded-lg border border-neutral-800 bg-neutral-900/40 p-3 text-xs text-neutral-400">
          This is a randomized (locally-administered) MAC — phones rotate these
          for privacy, so the same device may reappear under a different MAC.
        </p>
      )}

      {/* management */}
      <section className="mt-6 grid gap-4 sm:grid-cols-2">
        <form action={renameDevice} className="rounded-xl border border-neutral-800 p-4">
          <input type="hidden" name="mac" value={device.mac} />
          <label className="text-xs uppercase tracking-wide text-neutral-500">
            Custom name
          </label>
          <div className="mt-2 flex gap-2">
            <input
              name="custom_name"
              defaultValue={device.custom_name ?? ""}
              placeholder={device.hostname ?? "name this device"}
              className="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-sm outline-none focus:border-emerald-500"
            />
            <button className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-medium text-neutral-950 hover:bg-emerald-400">
              Save
            </button>
          </div>
        </form>

        <form action={setHidden} className="flex flex-col rounded-xl border border-neutral-800 p-4">
          <input type="hidden" name="mac" value={device.mac} />
          <input type="hidden" name="hidden" value={(!device.hidden).toString()} />
          <label className="text-xs uppercase tracking-wide text-neutral-500">Visibility</label>
          <p className="mt-2 text-sm text-neutral-400">
            {device.hidden ? "Hidden from the main list." : "Shown on the main list."}
          </p>
          <button className="mt-auto self-start rounded-lg border border-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-900">
            {device.hidden ? "Unhide" : "Hide"}
          </button>
        </form>
      </section>

      <form action={saveNotes} className="mt-4 rounded-xl border border-neutral-800 p-4">
        <input type="hidden" name="mac" value={device.mac} />
        <label className="text-xs uppercase tracking-wide text-neutral-500">Notes</label>
        <textarea
          name="notes"
          defaultValue={device.notes ?? ""}
          rows={2}
          placeholder="e.g. Kid's iPad — bedroom"
          className="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm outline-none focus:border-emerald-500"
        />
        <button className="mt-2 rounded-lg border border-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-900">
          Save notes
        </button>
      </form>

      {/* sessions */}
      <h2 className="mt-8 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Recent sessions
      </h2>
      <div className="mt-2 overflow-hidden rounded-xl border border-neutral-800">
        <table className="w-full text-sm">
          <tbody className="divide-y divide-neutral-800">
            {sessions.map((s, i) => (
              <tr key={i}>
                <td className="px-4 py-2 text-neutral-300">{fmtTime(s.started_at)}</td>
                <td className="px-4 py-2 text-neutral-500">
                  {s.ended_at ? `→ ${fmtTime(s.ended_at)}` : "→ now"}
                </td>
                <td className="px-4 py-2 text-right text-neutral-400">
                  {fmtDuration(sessionMs(s))}
                  {!s.ended_at && <span className="ml-1 text-emerald-400">●</span>}
                </td>
              </tr>
            ))}
            {sessions.length === 0 && (
              <tr>
                <td className="px-4 py-6 text-center text-neutral-500">No sessions recorded yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* raw event timeline */}
      <h2 className="mt-8 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        Event log
      </h2>
      <ul className="mt-2 space-y-1 text-sm">
        {events.map((e) => (
          <li key={e.id} className="flex items-center gap-3">
            <span
              className={`h-2 w-2 rounded-full ${e.type === "online" ? "bg-emerald-400" : "bg-neutral-600"}`}
            />
            <span className={e.type === "online" ? "text-emerald-400" : "text-neutral-400"}>
              {e.type}
            </span>
            <span className="text-neutral-500">{fmtTime(e.ts)}</span>
          </li>
        ))}
        {events.length === 0 && <li className="text-neutral-500">No events yet.</li>}
      </ul>
    </main>
  );
}

function Meta({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-neutral-500">{label}</dt>
      <dd className={`mt-0.5 ${mono ? "font-mono text-xs" : ""} text-neutral-200`}>{value}</dd>
    </div>
  );
}
