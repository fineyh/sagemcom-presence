import { login } from "@/app/actions";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <form
        action={login}
        className="w-full max-w-sm rounded-2xl border border-neutral-800 bg-neutral-900/60 p-8 shadow-xl"
      >
        <h1 className="text-xl font-semibold">Sagemcom Presence</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Enter the dashboard password.
        </p>
        <input
          type="password"
          name="password"
          autoFocus
          placeholder="Password"
          className="mt-6 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm outline-none focus:border-emerald-500"
        />
        {error && (
          <p className="mt-2 text-sm text-rose-400">Wrong password — try again.</p>
        )}
        <button
          type="submit"
          className="mt-4 w-full rounded-lg bg-emerald-500 px-3 py-2 text-sm font-medium text-neutral-950 hover:bg-emerald-400"
        >
          Unlock
        </button>
      </form>
    </main>
  );
}
