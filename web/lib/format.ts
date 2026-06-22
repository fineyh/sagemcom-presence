const TZ = "Australia/Sydney";

export function fmtDuration(ms: number): string {
  if (ms < 0 || !isFinite(ms)) ms = 0;
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s}s`;
}

export function fmtAgo(iso: string | null): string {
  if (!iso) return "—";
  return `${fmtDuration(Date.now() - new Date(iso).getTime())} ago`;
}

export function fmtSince(iso: string | null): string {
  if (!iso) return "—";
  return fmtDuration(Date.now() - new Date(iso).getTime());
}

export function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-AU", {
    timeZone: TZ,
    hour12: false,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
