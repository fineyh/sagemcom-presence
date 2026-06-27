# sagemcom-presence

Self-hosted presence tracking for a **Sagemcom F@st** home modem (e.g. the
Belong / Telstra "Gateway"). See which devices are connected, when they came
on/offline, and for how long — viewable from anywhere.

## How it works

A cloud host **cannot reach the modem** — it lives on the home LAN behind NAT,
with no inbound route from the public internet. So the read happens on the LAN
and the data is pushed *outward* to the cloud (outbound HTTPS only, no
port-forwarding needed):

```
[ Home LAN ]                                  [ Cloud ]
 Sagemcom modem                                 Next.js dashboard (Vercel)
      |  POST /cgi/json-req (JSON API)               ^  reads
      v                                               |
 collector  (Python, on an always-on PC)  ------>   Supabase (Postgres)
   every 60s: read hosts, diff, push events       (outbound HTTPS only)
```

| Folder | What it is |
|---|---|
| `agent/` | Python collector — logs into the modem's JSON API, reads the `Device.Hosts.Host` table, diffs against the last poll, and writes online/offline events to Supabase. Runs on an always-on LAN machine. |
| `web/` | Next.js dashboard on Vercel — reads from Supabase, behind a password gate. |
| `supabase/` | Postgres schema (`schema.sql`). |

## Modem notes

Built and tested against a Sagemcom **FAST4353** ("Belong Gateway"). The
reverse-engineering that made it work — the `local_admin` account (not `admin`),
MD5 challenge-response login, inferring on/offline transitions by polling +
diffing (the firmware won't report *when* a device changed state), and coping
with MAC randomization — is written up in [`agent/NOTES.md`](agent/NOTES.md).
Login + reads use the [`sagemcom_api`](https://pypi.org/project/sagemcom-api/)
library.

## Setup

### 1. Validate the router read

```sh
cd agent
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
# edit .env → set ROUTER_PASSWORD to the modem ADMIN password (on the sticker),
# NOT the wifi password
python probe_router.py
```

If your devices print out with ONLINE/offline flags, the read works.

### 2. Database

Create a Supabase project and apply [`supabase/schema.sql`](supabase/schema.sql)
(SQL editor, or the Supabase CLI). RLS is on and no anon policies are created, so
the public anon key can read nothing.

### 3. Dashboard

```sh
cd web
npm install
cp .env.example .env.local    # fill SUPABASE_URL, SUPABASE_SERVICE_KEY, DASHBOARD_PASSWORD
npm run dev
```

Deploy to Vercel and set the same env vars in the project settings.

### 4. Run the collector (Windows)

The dashboard only updates while the collector is running somewhere on the LAN.
First get the deps and `.env` in place:

```powershell
cd agent
pip install -r requirements.txt
copy .env.example .env     # fill ROUTER_PASSWORD + the two SUPABASE_* values
python collector.py        # test it runs, then Ctrl-C
```

Then pick one of two ways to keep it running. **Don't run both** — you'd get two
collectors polling at once.

#### Option A — tray app (recommended for a personal/daily-use PC)

A system-tray controller with an obvious on/off switch, so a background poller
can never get "stuck on" on a machine you use every day:

```powershell
pythonw tray.py            # or just double-click start-tray.vbs
```

A tray icon appears (green = running, grey = stopped) and the collector starts
polling immediately. **Right-click** the icon for:

- **Start / Stop collector** — toggle without quitting the tray
- **Start on login** — checkbox; adds/removes a per-user registry "Run" entry
  (no admin required) so the tray (and collector) come back after a reboot
- **Open log** — opens `agent\collector.log`
- **Quit** — stops the collector and exits

The collector runs as a child process tied to a Windows *job object* with
KILL_ON_JOB_CLOSE: if the tray exits for **any** reason — Quit, logout, or even
Task Manager ending it — Windows kills the collector too. You can never end up
with an orphaned, invisible poller you can't stop.

#### Option B — boot service (for a dedicated, headless always-on box)

Runs at boot as SYSTEM with no one logged in, and restarts on crash:

```powershell
# run PowerShell as Administrator:
powershell -ExecutionPolicy Bypass -File install-windows-autostart.ps1
```

The task logs to `agent\collector.log`. Manage it via the
`SagemcomPresenceCollector` scheduled task (`Stop-ScheduledTask` /
`Disable-ScheduledTask`, or `install-windows-autostart.ps1 -Uninstall`). If you
later switch to the tray app, uninstall this task first.

## Security model

- All secrets live in environment variables (`.env` locally, project settings on
  Vercel) and are never committed — see [`.gitignore`](.gitignore).
- Supabase **RLS** is locked to `service_role`; the public anon key can read
  nothing.
- The dashboard is gated by `DASHBOARD_PASSWORD`.

## Tech stack

Python (`sagemcom_api`) · Supabase (Postgres) · Next.js · Vercel
