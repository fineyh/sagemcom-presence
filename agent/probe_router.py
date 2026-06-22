"""
Phase 1 — Router read validation.

Logs into the Sagemcom (Belong) modem via its JSON API, auto-detects the
password encryption method, and prints the connected-device table.

Run this ONCE on a machine that is on the same network as the modem to confirm
we can read it before building the full collector.

    cd agent
    pip install -r requirements.txt
    copy .env.example .env   # then edit .env and put your modem admin password
    python probe_router.py
"""

import asyncio
import dataclasses
import os

from dotenv import load_dotenv
from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod
from sagemcom_api.exceptions import (
    AuthenticationException,
    LoginRetryErrorException,
    LoginTimeoutException,
    MaximumSessionCountException,
    UnauthorizedException,
)

load_dotenv()

HOST = os.getenv("ROUTER_HOST", "10.0.0.138")
USERNAME = os.getenv("ROUTER_USERNAME", "admin")
PASSWORD = os.getenv("ROUTER_PASSWORD", "")

# This F@st 4353 firmware uses plain MD5 (confirmed from its gui-api.js), so try
# MD5 first — avoids a 15s timeout that SHA512 causes on this device.
METHODS_TO_TRY = [
    EncryptionMethod.MD5,
    EncryptionMethod.MD5_NONCE,
    EncryptionMethod.SHA512,
]


async def try_login(method: EncryptionMethod) -> SagemcomClient | None:
    """Return a logged-in client if this encryption method works, else None."""
    client = SagemcomClient(HOST, USERNAME, PASSWORD, method, ssl=False)
    try:
        await client.login()
        return client
    except (
        AuthenticationException,
        LoginRetryErrorException,
        LoginTimeoutException,
        UnauthorizedException,
    ):
        await client.close()
        return None
    except MaximumSessionCountException:
        await client.close()
        raise


def fmt_host(h) -> str:
    name = h.user_friendly_name or h.host_name or "(no name)"
    status = "ONLINE " if h.active else "offline"
    return (
        f"  [{status}] {str(h.phys_address):<18} {str(h.ip_address or '-'):<15} "
        f"{name:<24} via={h.interface_type or '-':<10} changed={h.active_last_change or '-'}"
    )


async def main() -> int:
    if not PASSWORD:
        print("ERROR: ROUTER_PASSWORD is not set. Copy .env.example to .env and fill it in.")
        return 1

    print(f"Connecting to {HOST} as '{USERNAME}' ...")

    client = None
    used_method = None
    for method in METHODS_TO_TRY:
        print(f"  trying encryption method: {method} ...")
        try:
            client = await try_login(method)
        except MaximumSessionCountException:
            print(
                "ERROR: Router reports too many active sessions. Log out of the "
                "router web UI (or wait a few minutes) and try again."
            )
            return 2
        if client:
            used_method = method
            break

    if not client:
        print(
            "\nERROR: Login failed with every encryption method.\n"
            "  - Double-check the password (the modem admin password, often on the\n"
            "    sticker, NOT your wifi password).\n"
            f"  - Confirm the username (tried '{USERNAME}'); set ROUTER_USERNAME if different."
        )
        return 3

    print(f"\nOK: logged in. Encryption method = {used_method}\n")

    try:
        info = await client.get_device_info()
        print("==== Device info ====")
        print(f"  manufacturer : {info.manufacturer}")
        print(f"  model        : {info.model_name} ({info.model_number})")
        print(f"  software     : {info.software_version}")
        print(f"  uptime (s)   : {info.up_time}")

        hosts = await client.get_hosts(only_active=False)
        active = [h for h in hosts if h.active]
        print(f"\n==== Hosts: {len(hosts)} known, {len(active)} active ====")
        for h in sorted(hosts, key=lambda x: (not x.active, str(x.ip_address))):
            print(fmt_host(h))

        # Dump the full field set of the first couple of hosts so we can see
        # exactly which fields this firmware populates (informs the DB schema).
        print("\n==== Raw fields of first host (for schema design) ====")
        if hosts:
            for k, v in dataclasses.asdict(hosts[0]).items():
                if v not in (None, "", [], {}):
                    print(f"  {k} = {v!r}")
    finally:
        try:
            await client.logout()
        finally:
            await client.close()

    print("\nDONE. If you see your devices above, the router read works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
