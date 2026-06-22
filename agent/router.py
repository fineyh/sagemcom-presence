"""Read the connected-device table from the Belong / Sagemcom F@st 4353 modem.

Auth facts (see NOTES.md): username is `local_admin` (not admin), encryption is
plain MD5, endpoint is POST /cgi/json-req.
"""

from __future__ import annotations

from dataclasses import dataclass

from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod


@dataclass
class HostInfo:
    mac: str               # normalized UPPERCASE
    ip: str | None
    hostname: str | None   # router-learned hostname, or None
    active: bool           # online / offline
    interface: str | None  # WiFi / Ethernet
    is_randomized: bool     # locally-administered (privacy) MAC


def normalize_mac(mac: str) -> str:
    return mac.strip().upper()


def is_randomized_mac(mac: str) -> bool:
    """True if the MAC is locally administered (phone privacy randomization).

    The locally-administered bit is bit 1 of the first octet -> the second hex
    digit is one of 2, 6, A, E.
    """
    try:
        first_octet = int(mac.split(":")[0], 16)
        return bool(first_octet & 0x02)
    except (ValueError, IndexError):
        return False


def _clean_hostname(h) -> str | None:
    """Drop hostnames that are just the MAC (the firmware's default placeholder)."""
    if not h.host_name:
        return None
    name = str(h.host_name).strip()
    if not name:
        return None
    if name.replace(":", "").lower() == str(h.phys_address or "").replace(":", "").lower():
        return None
    return name


async def read_hosts(host: str, username: str, password: str) -> list[HostInfo]:
    """Log in, read all hosts, log out. Raises on login/read failure."""
    client = SagemcomClient(host, username, password, EncryptionMethod.MD5, ssl=False)
    await client.login()
    try:
        raw_hosts = await client.get_hosts(only_active=False)
    finally:
        try:
            await client.logout()
        finally:
            await client.close()

    hosts: list[HostInfo] = []
    for h in raw_hosts:
        if not h.phys_address:
            continue
        mac = normalize_mac(h.phys_address)
        hosts.append(
            HostInfo(
                mac=mac,
                ip=h.ip_address or None,
                hostname=_clean_hostname(h),
                active=bool(h.active),
                interface=h.interface_type or None,
                is_randomized=is_randomized_mac(mac),
            )
        )
    return hosts
