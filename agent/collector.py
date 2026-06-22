"""sagemcom-presence collector (Phase 3).

Runs on an always-on machine on the home LAN. Every POLL_INTERVAL_SECONDS it
logs into the modem, reads the connected-device table, diffs against the last
known state in Supabase, and writes online/offline events. The router does NOT
report when a device changed state, so we infer transitions here by polling.

    pip install -r requirements.txt
    # fill .env (router creds + SUPABASE_URL + SUPABASE_SERVICE_KEY)
    python collector.py
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

from router import read_hosts

load_dotenv()

ROUTER_HOST = os.getenv("ROUTER_HOST", "10.0.0.138")
ROUTER_USERNAME = os.getenv("ROUTER_USERNAME", "local_admin")
ROUTER_PASSWORD = os.getenv("ROUTER_PASSWORD", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("collector")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Supabase:
    """Thin PostgREST client using the service key (bypasses RLS)."""

    def __init__(self, client: httpx.AsyncClient):
        self.c = client
        self.base = f"{SUPABASE_URL}/rest/v1"
        self.headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }

    async def online_macs(self) -> set[str]:
        r = await self.c.get(
            f"{self.base}/devices",
            params={"select": "mac", "is_online": "eq.true"},
            headers=self.headers,
        )
        r.raise_for_status()
        return {row["mac"] for row in r.json()}

    async def upsert_device(self, row: dict) -> None:
        # one device at a time so each payload can omit unknown (null) fields
        # without clobbering existing custom_name / notes / hostname.
        r = await self.c.post(
            f"{self.base}/devices",
            params={"on_conflict": "mac"},
            headers={**self.headers, "Prefer": "resolution=merge-duplicates,return=minimal"},
            json=[row],
        )
        r.raise_for_status()

    async def set_offline(self, mac: str) -> None:
        r = await self.c.patch(
            f"{self.base}/devices",
            params={"mac": f"eq.{mac}"},
            headers={**self.headers, "Prefer": "return=minimal"},
            json={"is_online": False, "updated_at": now_iso()},
        )
        r.raise_for_status()

    async def insert_events(self, events: list[dict]) -> None:
        if not events:
            return
        r = await self.c.post(
            f"{self.base}/events",
            headers={**self.headers, "Prefer": "return=minimal"},
            json=events,
        )
        r.raise_for_status()

    async def insert_poll(self, **fields) -> None:
        r = await self.c.post(
            f"{self.base}/polls",
            headers={**self.headers, "Prefer": "return=minimal"},
            json=[fields],
        )
        r.raise_for_status()


def device_payload(h, online: bool) -> dict:
    """Build a devices upsert row, omitting null fields so we never overwrite
    user-set data or a previously-good hostname with null."""
    row = {
        "mac": h.mac,
        "is_online": online,
        "is_randomized": h.is_randomized,
        "updated_at": now_iso(),
    }
    if h.hostname:
        row["hostname"] = h.hostname
    if h.ip:
        row["last_ip"] = h.ip
    if h.interface:
        row["interface"] = h.interface
    if online:
        row["last_seen"] = now_iso()
    return row


async def run_cycle(sb: Supabase) -> None:
    hosts = await read_hosts(ROUTER_HOST, ROUTER_USERNAME, ROUTER_PASSWORD)
    by_mac = {h.mac: h for h in hosts}
    now_online = {h.mac for h in hosts if h.active}

    prev_online = await sb.online_macs()
    newly_online = now_online - prev_online
    newly_offline = prev_online - now_online

    # 1) upsert every device we can see this cycle (so the device row exists
    #    before any event references it via FK).
    for h in hosts:
        await sb.upsert_device(device_payload(h, online=h.active))

    # 2) devices that were online but vanished from the table entirely still
    #    need their flag cleared.
    for mac in newly_offline:
        if mac not in by_mac:
            await sb.set_offline(mac)

    # 3) record transitions.
    events: list[dict] = []
    for mac in newly_online:
        h = by_mac.get(mac)
        events.append({"mac": mac, "type": "online",
                       "ip": h.ip if h else None,
                       "hostname": h.hostname if h else None})
    for mac in newly_offline:
        h = by_mac.get(mac)
        events.append({"mac": mac, "type": "offline",
                       "ip": h.ip if h else None,
                       "hostname": h.hostname if h else None})
    await sb.insert_events(events)

    await sb.insert_poll(active_count=len(now_online), total_count=len(hosts), ok=True)

    if newly_online or newly_offline:
        log.info(
            "%d online / %d known | +online: %s | -offline: %s",
            len(now_online), len(hosts),
            ", ".join(sorted(newly_online)) or "-",
            ", ".join(sorted(newly_offline)) or "-",
        )
    else:
        log.info("%d online / %d known | no changes", len(now_online), len(hosts))


async def main() -> int:
    missing = [n for n, v in {
        "ROUTER_PASSWORD": ROUTER_PASSWORD,
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_SERVICE_KEY": SUPABASE_KEY,
    }.items() if not v]
    if missing:
        log.error("Missing required .env values: %s", ", ".join(missing))
        return 1

    log.info("collector starting: router=%s user=%s interval=%ss",
             ROUTER_HOST, ROUTER_USERNAME, INTERVAL)

    async with httpx.AsyncClient(timeout=30) as client:
        sb = Supabase(client)
        while True:
            try:
                await run_cycle(sb)
            except Exception as exc:  # keep the loop alive; record the failure
                log.exception("cycle failed: %s", exc)
                try:
                    await sb.insert_poll(active_count=None, total_count=None,
                                         ok=False, error=str(exc)[:300])
                except Exception:
                    log.error("could not record failed poll")
            await asyncio.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
