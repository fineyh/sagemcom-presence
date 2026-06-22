// Password gate shared by proxy.ts (edge) and server actions (node).
// Uses Web Crypto (available in both runtimes) so the cookie value is a hash of
// the password — possessing it proves the user knew the password, and it can't
// be forged without it.

export const SESSION_COOKIE = "sp_session";

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// .trim() guards against trailing newlines/whitespace that can sneak into env
// vars (e.g. when piped in during setup).
export function dashboardPassword(): string {
  return (process.env.DASHBOARD_PASSWORD ?? "").trim();
}

/** The expected session-cookie value for the configured password. */
export async function sessionToken(): Promise<string> {
  const pw = dashboardPassword();
  const secret = (process.env.AUTH_SECRET ?? "").trim() || pw;
  return sha256Hex(`sagemcom-presence|${pw}|${secret}`);
}

export async function isAuthed(token: string | undefined | null): Promise<boolean> {
  if (!token || !dashboardPassword()) return false;
  return token === (await sessionToken());
}
