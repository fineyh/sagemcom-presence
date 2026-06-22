import { connection } from "next/server";
import Link from "next/link";
import {
  supabaseAdmin,
  displayName,
  type Device,
  type Poll,
  type Session,
} from "@/lib/supabase";
import { fmtAgo, fmtSince, fmtTime } from "@/lib/format";
import { logout } from "@/app/actions";
import AutoRefresh from "@/components/AutoRefresh";

const HEARTBEAT_STALE_MS = 3 * 60 * 1000;

export default async function Home() {
  await connection(); // always render fresh

  const sb = supabaseAdmin();
  const [devicesRes, pollRes, sessionsRes] = await Promise.all([
    sb
      .from("devices")
      .select("*")
      .eq("hidden", false)
      .order("is_online", { ascending: false })
      .order("last_seen", { ascending: false }),
    sb.from("polls").select("*").order("ts", { ascending: false }).limit(1),
    sb.from("device_sessions").select("mac, started_at").is("ended_at", null),
  ]);

  const devices = (devicesRes.data ?? []) as Device[];
  const lastPoll = (pollRes.data?.[0] ?? null) as Poll | null;
  const openSince = new Map<string, string>();
  for (const s of (sessionsRes.data ?? []) as Pick<Session, "mac" | "started_at">[]) {
    const prev = openSince.get(s.mac);
    if (!prev || s.started_at > prev) openSince.set(s.mac, s.started_at);
  }

  const onlineCount = devices.filter((d) => d.is_online).length;
  const pollAgeMs = lastPoll ? Date.now() - new Date(lastPoll.ts).getTime() : Infinity;
  const collectorLive = lastPoll != null && lastPoll.ok && pollAgeMs < HEARTBEAT_STALE_MS;

  return (
    <main className="mx-auto max-w-4xl p-4 sm:p-8">
      <AutoRefresh seconds={30} />

      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Sagemcom Presence</h1>
          <p className="text-sm text-neutral-400">
            <span className="text-emerald-400">{onlineCount} online</span>
            <span className="text-neutral-600"> · </span>
            {devices.length} known
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
              collectorLive
                ? "border-emerald-900 bg-emerald-950/50 text-emerald-300"
                : "border-amber-900 bg-amber-950/50 text-amber-300"
            }`}
            title={lastPoll ? `last poll ${fmtTime(lastPoll.ts)}` : "no polls yet"}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                collectorLive ? "bg-emerald-400" : "bg-amber-400"
              }`}
            />
            {collectorLive
              ? `collector live · ${fmtAgo(lastPoll!.ts)}`
              : lastPoll
                ? `collector stale · ${fmtAgo(lastPoll.ts)}`
                : "collector offline"}
          </span>
          <form action={logout}>
            <button className="rounded-lg border border-neutral-800 px-3 py-1 text-xs text-neutral-400 hover:bg-neutral-900">
              Log out
            </button>
          </form>
        </div>
      </header>

      <section className="mt-6 overflow-hidden rounded-xl border border-neutral-800">
        <table className="w-full text-sm">
          <thead className="bg-neutral-900/60 text-left text-xs uppercase tracking-wide text-neutral-500">
            <tr>
              <th className="px-4 py-2 font-medium">Device</th>
              <th className="px-4 py-2 font-medium">IP</th>
              <th className="hidden px-4 py-2 font-medium sm:table-cell">Link</th>
              <th className="px-4 py-2 text-right font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-800">
            {devices.map((d) => (
              <tr key={d.mac} className="hover:bg-neutral-900/40">
                <td className="px-4 py-3">
                  <Link href={`/device/${encodeURIComponent(d.mac)}`} className="group">
                    <div className="flex items-center gap-2">
                      <span
                        className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                          d.is_online ? "bg-emerald-400" : "bg-neutral-600"
                        }`}
                      />
                      <span className="font-medium group-hover:underline">
                        {displayName(d)}
                      </span>
                      {d.is_randomized && (
                        <span
                          className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] text-neutral-400"
                          title="Locally-administered (randomized) MAC — identity may be unstable"
                        >
                          random MAC
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 font-mono text-xs text-neutral-500">{d.mac}</div>
                  </Link>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-neutral-400">
                  {d.last_ip ?? "—"}
                </td>
                <td className="hidden px-4 py-3 text-neutral-400 sm:table-cell">
                  {d.interface ?? "—"}
                </td>
                <td className="px-4 py-3 text-right">
                  {d.is_online ? (
                    <span className="text-emerald-400">
                      online · {fmtSince(openSince.get(d.mac) ?? d.last_seen)}
                    </span>
                  ) : (
                    <span className="text-neutral-500">seen {fmtAgo(d.last_seen)}</span>
                  )}
                </td>
              </tr>
            ))}
            {devices.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-neutral-500">
                  No devices yet. Make sure the collector is running.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>

      <p className="mt-4 text-center text-xs text-neutral-600">auto-refreshes every 30s</p>
    </main>
  );
}
