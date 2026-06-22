# Router integration notes — Belong / Sagemcom F@st 4353

Hard-won facts from reverse-engineering the modem's JSON API. Keep these; they
were not obvious and cost real effort to find.

## Identity / auth

| | |
|---|---|
| Model | Sagemcom **FAST4353** ("Belong Gateway"), firmware `SG7M100000186` |
| Admin URL | `http://10.0.0.138` → GUI at `/0.1/gui/` |
| API endpoint | `POST /cgi/json-req` |
| **Username** | **`local_admin`** — NOT `admin`. This was the whole battle. |
| Password | the modem admin password (sticker), in `.env` as `ROUTER_PASSWORD` |
| Encryption | **MD5** (`EncryptionMethod.MD5`). SHA512 just times out on this firmware. |
| basicAuth | `false` — hashed challenge flow, no plaintext password in the payload |

### The `admin` trap

Logging in as `admin` returns the **misleading** error
`"Access denied via this network interface"` (code 16777226 /
`XMO_ACCESS_RESTRICTION_ERR`) — it looks like a firewall/interface block, but it
is really "this account can't admin from here." The correct local account is
`local_admin` (found in the GUI's own `session` cookie: `{user:"local_admin",
basic:false, ...}`). With the right username, the stock `sagemcom_api` library
logs in fine — no patching needed.

### Library quirk (cosmetic)

`sagemcom_api` 1.4.3 compares error *descriptions* against `XMO_*` constant
*names*, but this firmware returns human strings ("Action error", "Access denied
via this network interface"). So a failed login can surface as a raw
`KeyError: 'id'` instead of a clean exception. Not a problem on the happy path.

## Data shape (`get_hosts`)

Per host we get: `phys_address` (MAC), `ip_address`, `host_name`,
`user_friendly_name`, `active` (bool = online/offline), `interface_type`,
`address_source`, `lease_*`. The xpath query language is slash-style, e.g.
`Device/Hosts/...`, `Device/IP/Interfaces/Interface[Alias="IP_DATA"]/Status`.

### Two realities that shape the design

1. **`active_last_change` is empty** on this firmware — the router will NOT tell
   us *when* a device went on/offline. The collector must infer on/offline
   transitions itself by polling and diffing snapshots over time.
2. **MAC randomization** — phones present locally-administered random MACs
   (2nd hex nibble is 2/6/a/e, e.g. `c2:`, `1e:`, `da:`). The same phone can
   reappear under a new MAC, so MAC is not a stable identity. The dashboard lets
   the user rename/merge devices to cope.
