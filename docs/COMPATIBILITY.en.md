*[Français](COMPATIBILITY.md) · **English***

# Compatibility

Everything here has been **verified against a real instance**, not deduced from the
documentation. Image tags are pinned in `src/plugarr/catalog.py`.

Last verification campaign: **2026-08-31**, Docker Engine 29.6.1, Docker Compose v5.3.0,
Docker Desktop on Windows 11 (WSL2 backend).

## Versions tested

| Service | Image | Tag | Version reported by the API |
|---|---|---|---|
| Sonarr | `lscr.io/linuxserver/sonarr` | `4.0.19` | 4.0.19.2979 |
| Radarr | `lscr.io/linuxserver/radarr` | `6.3.0` | verified at startup |
| Prowlarr | `lscr.io/linuxserver/prowlarr` | `2.5.2` | verified at startup |
| Transmission | `lscr.io/linuxserver/transmission` | `4.1.3` | — |
| Jellyfin | `lscr.io/linuxserver/jellyfin` | `10.11.11` | 10.11.11 |
| Lidarr | `lscr.io/linuxserver/lidarr` | `3.1.0` | 3.1.0.4875 |
| qBittorrent | `lscr.io/linuxserver/qbittorrent` | `5.2.3` | v5.2.3 |
| Flood | `jesec/flood` | `4.16.1` | not tested yet |

## Findings verified experimentally

### Pre-seeding `config.xml` works

A `config.xml` written **before** the first start is adopted by the application. Sonarr
keeps our fields and merely adds its own (`EnableSsl`). Our API key answers immediately on
`/api/v3/system/status`.

The first start takes **about 110 s** (image extraction + initialisation). That is what
sets the default timeout to 300 s.

### `Forms` + `Enabled` is the right authentication setting

Three behaviours confirmed on Sonarr 4.0.19.2979:

| Request | Result |
|---|---|
| `GET /` with no session | `302` to `/login` — the UI is protected |
| `GET /api/v3/system/status` with no key | `401` |
| `GET /api/v3/system/status` with `X-Api-Key` | `200`, `"authentication": "forms"` |

The alternative `External` + `DisabledForLocalAddresses` wires just as well but leaves the
web UIs open to the whole local network. **Rejected.**

Bonus: the application consumes `<Username>`/`<Password>` on first start, migrates them to
its database, then **erases them from the file**. The cleartext password does not survive
on disk.

### `Category` and `Directory` are mutually exclusive

Setting both makes the download client creation fail:

```
HTTP 400 — propertyName: "TvCategory", errorMessage: "Cannot use Category and Directory"
```

**Trap**: the template returned by `/schema` arrives with a **default category already
filled in** (`tv-sonarr` for Sonarr, `radarr` for Radarr). Omitting the field is not
enough, it must be **explicitly emptied**.

PlugArr keeps `Directory`, which points at an explicit path under `/data/torrents` and
keeps hardlinks possible.

### The Jellyfin notification requires an API key

Sonarr's and Radarr's `MediaBrowser` implementation refuses an empty `apiKey`:

```
HTTP 400 — propertyName: "ApiKey", errorMessage: "'Api Key' must not be empty."
```

PlugArr therefore creates a Jellyfin key through `POST /Auth/Keys?app=plugarr` (answers
`204`) during the wizard step, then reads it back with `GET /Auth/Keys`, and injects it
into the notifications. That is what forces the order: Jellyfin before the notifications.

### Jellyfin 10.11.11 startup wizard

| Call | Code |
|---|---|
| `POST /Startup/Configuration` | `204` |
| `GET /Startup/User` | `200` |
| `POST /Startup/User` | `204` |
| `POST /Startup/RemoteAccess` | `204` |
| `POST /Startup/Complete` | `204` |
| `POST /Users/AuthenticateByName` | `200` + `AccessToken` |
| `POST /Library/VirtualFolders` | `204` |

After which `StartupWizardCompleted` turns `true` and the library appears with the right
`CollectionType` and the right path.

Jellyfin starts in **about 25 s**, noticeably faster than the *arr.

## Final wiring verification

Every link is validated by the relevant application's **Test** button, not by the POST's
return code:

| Test | Result |
|---|---|
| `POST /api/v3/downloadclient/test` (Sonarr → Transmission) | `200` |
| `POST /api/v1/applications/test` (Prowlarr → Sonarr) | `200` |
| `POST /api/v3/notification/test` (Sonarr → Jellyfin) | `200` |
| `GET /api/v3/rootfolder` | `accessible: true` |

Clean installation from scratch: **10/10 links established**.

## Phase 2 — verified findings

Campaign of **2026-08-31**, same environment. Clean 7-service installation with **both
download clients in parallel**: **18/18 links established**.

### Pre-seeding the qBittorrent password works

Since 4.6.1, qBittorrent generates a random temporary password on first start and writes it
to standard output — impossible to wire automatically.

Writing `WebUI\Password_PBKDF2` into `/config/qBittorrent/qBittorrent.conf` before the
first start solves the problem. Format confirmed against 5.2.3:

```
@ByteArray(<base64 salt>:<base64 hash>)
PBKDF2-HMAC-SHA512, 100000 iterations, 64-byte key, 16-byte salt
```

Result: `POST /api/v2/auth/login` answers `204` with a `QBT_SID` cookie, and no temporary
password appears in the logs.

**Watch the return code**: qBittorrent 5.x returns `204` on success and `200` with the body
`Fails.` on failure. So it is the presence of the cookie that counts, never the HTTP code
alone.

### `HostHeaderValidation` must be disabled

Sonarr and Radarr call qBittorrent by its container name (`http://qbittorrent:8080`), not
by an IP address. Without `WebUI\HostHeaderValidation=false`, qBittorrent rejects those
requests.

### qBittorrent routes by category, Transmission by directory

Transmission has no real categories: it gets a `Directory`. qBittorrent has native
categories with a per-category save path: it gets a `Category`, created beforehand through
`POST /api/v2/torrents/createCategory`.

Forced ordering: the categories must exist **before** the *arr point at them, otherwise
qBittorrent creates them itself with no save path. Prowlarr does the same with a `prowlarr`
category: it is therefore pre-created too.

Verified after installation:

```
movies   -> /data/torrents/movies
music    -> /data/torrents/music
prowlarr -> /data/torrents
tv       -> /data/torrents/tv
```

### Lidarr is not just another Sonarr

Three differences that break code written for Sonarr and Radarr:

1. **Its API is `v1`**, not `v3`.
2. **Its root folder requires more fields.** Where Sonarr accepts `{"path": ...}`, Lidarr
   answers `400`:

   ```
   Name                     : 'Name' must not be empty.
   DefaultQualityProfileId  : must be greater than '0'.
   DefaultMetadataProfileId : must be greater than '0'.
   ```

   There is no `/schema` for `rootfolder`. Profile ids are not stable across versions: they
   are resolved **by name** (`Standard`), falling back to the first available profile.

3. Lidarr does **not** expose the `MediaBrowser` notification implementation: no
   Lidarr-to-Jellyfin link is attempted.

## PUID / PGID per platform — verified

The starting point was a `TODO(verify)`. The verification showed that **the question was
badly framed**: it was not the same values that had to be found, but two different
behaviours.

| Profile | Behaviour | Why |
|---|---|---|
| `generic-linux` | detection (`os.getuid`) | the current user is the right one |
| `unraid` | **constant 99:100** | Unraid runs its containers as `nobody:users` platform-wide, and its `appdata` belongs to 99:100 |
| `synology` | detection | **DSM UIDs vary with the order users were created**: 1026 for the first one, but much higher values are common |

Hardcoding `1026` for Synology was therefore **wrong by design**, not merely unverified. A
constant cannot be right when the value depends on the installation.

Two consequences in the code:

- `detect_ids()` returns `None` when the platform does not expose `os.getuid` (Windows),
  instead of silently inventing `1000:1000`. A fabricated value that says nothing prevents
  warning the user.
- `StackConfig` carries `ids_source` and `ids_certain`. The summary shows where the values
  come from ("detected", "Unraid constant", "fallback"), and the wizard warns explicitly
  when detection failed.

Sources: [Unraid forums](https://forums.unraid.net/topic/117661-docker-user-puid-and-group-pgid-settings/)
· [Marius Hosting, UID/GID on Synology](https://mariushosting.com/synology-how-to-find-uid-userid-and-gid-groupid/)

## Coexistence with an existing stack — verified

Observed on a real Unraid running 75 containers, including a `sonarr` on port 8989 with
`/mnt/user/appdata/sonarr` as its configuration: **PlugArr hardcoded `container_name`**, so
it could neither coexist with an existing stack nor be deployed twice on the same machine.

Container names are now prefixed with the project name (`plugarr-sonarr`). Verified against
Docker Compose v5.3 that this breaks nothing:

```
from the "sonarr" service:
  getent hosts prowlarr           -> 172.18.0.3  prowlarr
  getent hosts dnsprobe-prowlarr  -> 172.18.0.3  dnsprobe-prowlarr
```

The **service name** resolves independently of `container_name`. The wiring targets the
service (`http://sonarr:8989`), so it is unaffected.

**Port** collisions remain possible (8989 is a very common default): the preflight detects
them and refuses before anything is written.

## Native Linux — verified on 2026-08-31

Every previous campaign ran on Docker Desktop / WSL2, where permissions are more permissive
than on a real server. Verification done on a **Proxmox LXC running Debian 12.2**
(PVE 9.2.6), ext4, Docker 29.7.2.

| | |
|---|---|
| Full installation (5 services) | **11/11 links established**, all validated by the Test button |
| Second pass | nothing created, everything "already present" |
| Hardlink `/data/torrents/tv` → `/data/media/tv`, **from inside the Sonarr container** | `stat -c %h` = **2** |

The hardlink is the missing proof: on Windows, only `os.link` on the host side had been
tested. Here it is Sonarr itself, in its container, on ext4, sharing the inode between the
downloads and the media library. That is exactly what the single `/data` mount is supposed
to guarantee.

### Docker inside an LXC: `nesting=1` is enough

Contrary to what is often written, `keyctl=1` was not necessary — and it is not settable
through a Proxmox API token anyway, only as `root@pam` directly. With `nesting=1` alone,
`docker run hello-world` and the full stack work.

### The bug only Linux could reveal

`sudo plugarr install` detected `0:0` and ran **the whole stack as root**, silently.
Downloaded media then belongs to root, and the user can no longer touch it without `sudo`.

`resolve_ids` now flags the root case explicitly, the same way it flags an impossible
detection. The value is still offered — it is a legitimate choice on some NAS devices — but
it is no longer silent.

## Not verified to date

- Bazarr is **deliberately absent from the catalogue**: its configuration goes through a
  YAML file rather than an API, and nothing has been verified yet. The project does not ship
  a service it cannot wire.
- Flood has not yet been started in a test campaign.

## Indexers — verified findings (Prowlarr 2.5.2)

### What Prowlarr ships

`GET /api/v1/indexer/schema` returns **626 definitions**, i.e. **5.7 MB** — to be loaded
once and cached, never on every keystroke.

| | |
|---|---|
| private | 475 |
| public | 88 |
| semi-private | 63 |
| torrent / usenet | 605 / 21 |

### Spotting credential fields

The field-level `privacy` marker (`apiKey`, `password`, `userName`) only covers **115 fields
out of more than 9,500**: most Cardigann definitions leave their keys at `privacy: normal`.
A combined heuristic is necessary:

1. `privacy` ∈ (`apiKey`, `password`, `userName`)
2. or `type == "password"`
3. or a known name (`apikey`, `passkey`, `cookie`, `rsskey`, …)
4. or — **structural rule** — `type == "textbox"` with an empty default value
5. while excluding the settings prefixes (`baseSettings.`, `torrentBaseSettings.`,
   `usenetBaseSettings.`), the 882 purely decorative `type: "info"` fields, and a short list
   of free text areas that are not credentials (`vipExpiration`, `additionalParameters`,
   language preferences)

### The audit that produced rule 4

Rules 1 to 3 were run against the **626 definitions** by
[`scripts/audit_indexers.py`](../scripts/audit_indexers.py). They let six credentials
through: `mamId` (MyAnonamouse), `twoFactorAuthCode`, `alt2fatoken`, `passan`, `staffpass`,
`csrf_token`.

All of them were **text areas with no default value**. Hence the structural rule, which is
better than an endless list of names: an empty textbox is, by construction, something only
the user can supply. Behaviour settings are checkboxes or lists, never empty textboxes.

Measured effect: **58 fields** caught across the 626 definitions, all real credentials
(26 2FA codes, 17 `useragent`, 8 `pin`, `mamId`, `passan`, `staffpass`…). No form has more
than **3 credentials**.

Two families of cases were examined and then judged correct:

- **4 private indexers with no credentials at all** — `BitMagnet (Local DHT)`, `comicat`,
  `MioBT`, `ConCen`. These are search engines that require no account.
- **6 misleadingly named fields** — `useFreeleechToken`, `usetoken`, `passid`… all
  checkboxes or lists, therefore settings.

The audit runs in CI against the test stack's Prowlarr: **it fails if a future version
introduces a credential field in an unexpected shape.**

### The URLs are not in the `baseUrl` field

**600 of the 626** definitions expose a `select` `baseUrl` **with no value and no
`selectOptions`**. The addresses live at definition level, in `indexerUrls`. Without picking
them up there, the user would have to guess the tracker's address. Only 3 definitions
legitimately have no URL: the generic ones (`Generic Newznab`, `Generic Torznab`,
`Torrent RSS Feed`).

### Adding one necessarily contacts the indexer

`appProfileId` must be `> 0`, like Lidarr's root folder. Resolved by name (`Standard`),
never hardcoded.

Above all: **`forceSave=true` does not skip validation.** Verified on two failure cases:

| Situation | Result |
|---|---|
| unreachable indexer | `400 — Unable to connect to indexer` |
| test search with no result | `400 — Query successful, but no results were returned` |
| fake local Torznab indexer returning a result | saved |

There is therefore **no way to register an indexer offline**. That is not a plugarr choice.
The upside is useful: the validation *is* the test, so a successful addition proves the
credentials work.

Verification carried out against a **fake local Torznab server**, never against a real
tracker.

## Seerr replaces Jellyseerr and Overseerr — verified on 2026-08-31

Reported by a user, verified rather than assumed. This is not a rename but a **merger of the
two projects**, announced on 10 February 2026.

| | |
|---|---|
| Canonical repository | `seerr-team/seerr` — 12,440 stars, active |
| Image | `seerr/seerr`, latest stable version **v3.4.1** (2026-07-30) |
| `sct/overseerr` | **archived**, last push 2026-02-15 |
| `fallenbagel/jellyseerr` | redirects (HTTP 301) to `seerr-team/seerr` |

Seerr covers Jellyfin, Emby **and** Plex — the two original projects split those targets
between them — and migrates the data automatically on first start.

Consequence for PlugArr: the roadmap now targets a single user-request service. Planning for
taking over an existing Jellyseerr or Overseerr installation is pointless: Seerr does it
itself.

## Taking over an existing stack — verified on 2026-08-31

Tested against a stack **PlugArr did not create**: four containers with arbitrary names,
spread across **two different Docker networks**, including two Sonarrs.

Result: `prowlarr → sonarr` established and validated by the Test button, on foreign
containers, with API keys read from their `config.xml` files.

Three design mistakes that only the real test revealed.

### Do not impose your own directory tree

The first attempt failed: `Path '/data/media/tv' does not exist`. PlugArr was applying its
own tree to a stack that has its own.

**Adopting means wiring services together, not reorganising somebody's folders.** Existing
root folders are now read and respected; when there is none, PlugArr says so instead of
inventing one. Same rule for qBittorrent categories: overwriting them would move downloads
in progress.

### `localhost` means nothing between containers

Second failure: `Unable to complete application test, cannot connect to Sonarr`. The adopted
services live on their own networks — the compose service name does not resolve there — and
**from inside a container, `localhost` means that container**, not the machine.

`adopt` therefore detects the machine's address on the local network, and refuses to
continue if it cannot rather than wiring dead URLs.

### A container name proves nothing

`looks_like_plugarr` recognised its own containers by their name (`<project>-<service>`). A
test showed that `my-sonarr` matched: PlugArr was **silently skipping a container that did
not belong to it**.

Generated services now carry a `plugarr.managed=true` label, and the detection reads it
instead of guessing.

### What stays out of reach

An existing download client's password is hashed in its configuration: unreadable.
`--dl-user` and `--dl-pass` ask for it explicitly, and the step fails with a clear message
rather than a technical error.

## autobrr and qui — verified on 2026-08-31

Reported by a user, from [github.com/autobrr](https://github.com/autobrr).

| | |
|---|---|
| autobrr | `ghcr.io/autobrr/autobrr:v1.85.0`, port **7474** |
| qui | `ghcr.io/autobrr/qui:v1.27.0`, port **7476** |

### Four autobrr quirks, none of them guessable

**The authentication header is `X-API-Token`**, not `X-Api-Key` like the *arr. The wrong
header gives a `403` with no explanation. Verified by trying all three.

**An API key requires a `scopes` field.** Without it, creation fails with a `500` on an SQL
constraint: `NOT NULL constraint failed: api_key.scopes`. The error message is in fact what
made it possible to find the missing field.

**Sonarr, Radarr and Lidarr are "download clients".** autobrr does not distinguish
applications from clients: same `POST /api/download_clients` endpoint, only the `type`
changes. Types confirmed one by one: `SONARR`, `RADARR`, `LIDARR`, `QBITTORRENT`,
`TRANSMISSION`, `DELUGE_V2`, `SABNZBD`, `WHISPARR`, `READARR`.

**The setup can only be played once.** `GET /api/auth/onboard` returns `204` as long as no
account exists, then `503 — user already registered`. That is what makes the step
replayable.

### A warning that does not apply to the container

The documentation warns that autobrr listens on `127.0.0.1` by default, which would make a
container unreachable. **Verified: the image generates `host = "0.0.0.0"`.** The warning
applies to a non-container installation.

### Result

Real installation with Sonarr and qBittorrent: autobrr created, account initialised, API key
generated, both services declared — and **both connection tests triggered by autobrr itself
answer `204`**.

`qui` does listen on 7476, confirmed by its own logs. It is a UI: it discovers its
qBittorrent instances through its configuration screen, no automatic wiring is possible.

## Gluetun — verified on 2026-08-31

| | |
|---|---|
| Image | `qmcgaw/gluetun:v3.41.3` |
| Repository | `qdm12/gluetun` **redirects to `passteque/gluetun`** — 15,356 stars, active |
| Healthcheck | provided by the image: `/gluetun-entrypoint healthcheck`, 5 s, 3 attempts |

### The provider list comes from Gluetun

Rather than copying a list out of an article, we passed it an invalid name. It answers with
the exact enumeration: `airvpn, cyberghost, expressvpn, fastestvpn, giganews, hidemyass,
ipvanish, ivpn, mullvad, nordvpn, perfect privacy, privado, private internet access,
privatevpn, protonvpn, purevpn, slickvpn, surfshark, torguard, vpnsecure, vpn unlimited,
vyprvpn, windscribe, custom, pia`.

That is the list that lives in `models.py`, and `plugarr vpn-providers` displays it.

### The two modes do not require the same fields

Observed by starting Gluetun empty and reading what it demands:

| Mode | What it requires |
|---|---|
| `wireguard` | `WIREGUARD_PRIVATE_KEY`, and a **real base64 key** — it refuses any other string |
| `openvpn` | `OPENVPN_USER` and `OPENVPN_PASSWORD` |

### Two traps of `network_mode: service:`

**The client's ports must move onto Gluetun.** A container sharing another one's network
stack no longer has a stack of its own: it *cannot* publish a port any more. Without that
transfer, the client's UI becomes unreachable — a silent and confusing failure.

**The client loses its DNS alias.** Verified against Docker Compose 5.3 with two dummy
containers:

```
from a third container:
  getent hosts client    -> nothing
  getent hosts fake-vpn  -> 172.18.0.2
```

`http://qbittorrent:8080` therefore no longer resolves: the wiring must target
`http://gluetun:8080`. Without that correction, enabling the VPN silently broke all the
wiring.

### The property that matters: no leak is possible

Tested with deliberately wrong credentials:

```
gluetun      running  Up 47 seconds (unhealthy)
qbittorrent  created  Created
dependency failed to start: container plugarr-gluetun is unhealthy
```

**The download client does not start until the tunnel is up.** That is not an intention, it
is the observed behaviour: `depends_on` on Gluetun's healthcheck closes the door before a
single packet can leave outside the VPN.


## Incoming port and OpenVPN mode — verified on 2026-09-09

Everything below was provoked against `qmcgaw/gluetun:v3.41.3`, the pinned image,
with a real ProtonVPN account and Swiss servers.

### `VPN_PORT_FORWARDING=on` already restricts the selection

`PORT_FORWARD_ONLY` does not need to be set. With `VPN_PORT_FORWARDING=on` alone,
Gluetun prints in its startup summary:

```
|   |   |   ├── Port forwarding only servers: yes
```

A probe on a country without an incoming port therefore fails the same way with
or without the flag, and it is a **definitive** refusal:

```
ERROR [vpn] finding a VPN server: filtering servers: no server found:
for VPN wireguard; protocol udp; country macedonia; port forwarding only
```

That is why the wizard only offers locations that provide one: the tunnel would
not start at all.

### OpenVPN mode works, incoming port included

| | |
|---|---|
| Tunnel | established in **14 s** by `vpnessai`, exit `Switzerland`, `AS209103 Proton AG` |
| Incoming port | `[port forwarding] port forwarded is 47878` |
| Username | as entered, **without** any suffix |

### The `+pmp` suffix is not required, contrary to what Gluetun suggests

The binary carries this string, emitted by
`internal/provider/protonvpn/portforward.go`:

```
%w - make sure you have +pmp at the end of your OpenVPN username
```

The code does **not** check the suffix: it suggests it after a `connection
refused` on NAT-PMP. Both variants were tried on the same account, minutes apart:

| Username | Tunnel | Port obtained |
|---|---|---|
| `<user>` | yes | 47878 |
| `<user>+pmp` | yes | 44793 |

PlugArr therefore does **not** alter the username you entered: that would be a
bet, and an account where Proton rejected the suffix would end up with no tunnel
at all. The suffix is only mentioned where it answers something — when the check
finds that no port was obtained.

### OpenVPN is structurally slower to reach a verdict

The TLS negotiation timeout is a firm **sixty seconds** per silent server,
decided by OpenVPN 2.6 and not configurable here:

```
WARN [openvpn] TLS Error: TLS key negotiation failed to occur within 60 seconds
```

Hitting a silent server is not exceptional: the server list bundled in the image
was stamped **2025-11-18** while the image was built on 2026-07-30, and one of
the nine Swiss port-forwarding servers (`node-ch-03`, `62.169.136.3`) no longer
answered.

Timeline measured with a deliberately wrong password:

```
00 s  first server, silent
60 s  TLS Error: TLS key negotiation failed
75 s  second server
93 s  ERROR [openvpn] AUTH: Received control message: AUTH_FAILED
```

At forty-five seconds the trial expired **before** Gluetun had said anything, and
returned "maybe" on a certain answer. Hence two minutes over OpenVPN, forty-five
seconds over WireGuard.

### A rejected authentication is recognisable

`AUTH_FAILED` is the OpenVPN equivalent of an unreadable WireGuard key: the
server read the credentials and rejected them, and no amount of waiting will make
them good. The marker carries the underscore (`auth_failed`) rather than the word
alone, because the log contains `AUTH: Received control message` and
`Authentication file path` in perfectly normal lines.

### Setting the port is an EVENT, not a poll — verified on 2026-09-10

`VPN_PORT_FORWARDING_UP_COMMAND` does exist in v3.41.3 (read off the binary) and Gluetun
calls it **one second** after obtaining the port, with the value substituted:

```
2026-09-10T10:50:27Z INFO [port forwarding] port forwarded is 45726
up-command appele avec le port 45726 a Thu Sep 10 10:50:28 UTC 2026
```

That is why PlugArr ships no third-party mod polling Gluetun's API in a loop. An event
does have a blind spot, and it is real: if the client is recreated **between two
attributions**, no call happens and it keeps its default port until the lease is renewed.
`plugarr doctor` therefore replays the script itself when it sees the gap.

### `wget` is not the same everywhere

| Image | `wget` | `--save-cookies` |
|---|---|---|
| `qmcgaw/gluetun:v3.41.3` | GNU Wget 1.25.0 | yes |
| `lscr.io/linuxserver/qbittorrent:5.2.3` | BusyBox 1.37.0 | **no** |

The sync script talks to qBittorrent's API, which requires keeping a session cookie. It
runs **inside Gluetun**, the only one of the two carrying a real `wget` — an equivalent
script placed in the qBittorrent container could not authenticate with the same tools.

### qBittorrent 5.2.3: `web_ui_api_key` exists and does nothing

Verified against a real instance, WebAPI **2.15.1**. The key shows up in the preferences:

```
"web_ui_api_key":""
```

But it is **inert** in this version:

- `POST app/setPreferences` with `web_ui_api_key` is accepted and the value read back stays empty;
- no dedicated endpoint (`app/apiKeys`, `app/generateApiKey`, … all answer **404**);
- set by hand in `qBittorrent.conf` (`WebUI\APIKey=…`), header authentication still fails —
  `X-Api-Key`, `X-API-Key` and `Authorization` all return **403**.

Authentication therefore goes through `api/v2/auth/login`, username and password. To
revisit when a qBittorrent release makes that field functional.

Two traps along the way, both observed by querying the instance:

- the WebUI **validates the `Host` header**. From the host on a different published port,
  everything answers `Unauthorized` until you force `Host: localhost:8080`;
- it **bans after five failed** authentications (`web_ui_max_auth_fail_count: 5`), which is
  why the wiring never tries more than four passwords.

### The artefacts and their permissions

Read off the test bench, and confirmed by searching for every secret in the
generated text:

| File | Mode | Secrets in clear |
|---|---|---|
| `.env` | 600 | all of them |
| `stack.yml` (and its history) | 600 | all of them |
| `docker-compose.yml` | 644 | **none** — it only carries `${REFERENCES}` |
| `${CONFIG_ROOT}/gluetun/port-sync.sh` | 755 | none — it reads `$QBT_PASS` from the environment |

## Update detection — verified on 2026-08-31

### Two different things are called "an update"

| | How you see it | What it requires |
|---|---|---|
| **Rebuild** | local digest != remote digest, same tag | `pull` + recreate |
| **New version** | a newer tag exists | change the tag, therefore rewrite `stack.yml` |

LinuxServer republishes its images very often. Confusing the two would make the information
useless.

### The deployed tag had to leave the code

PlugArr pinned its tags in `catalog.py`. Unintended consequence: **nobody could have updated
Sonarr without waiting for a new version of the tool.** The tag now lives in `stack.yml`;
the catalogue only provides the initial value.

### Listing tags: pagination is not a detail

The registry v2 protocol returns tags in **publication** order — oldest first, in pages of
200. Measured on `linuxserver/sonarr`: 25 pages and **6.2 seconds** were not enough to reach
the current version; the listing was still stopping on Sonarr 3.x tags.

Chosen solution: when the repository is also on Docker Hub, its API accepts
`ordering=last_updated` and gives the most recent ones first — one page is enough. The
generic protocol remains the fallback for other registries.

**`lscr.io` really is a Docker Hub mirror**, verified by comparing digests:
`lscr.io/linuxserver/sonarr:4.0.19` and `linuxserver/sonarr:4.0.19` return the same sha256.
That is what makes the shortcut legitimate.

Measurements after the fix, across three registries:

| Image | Time | Result |
|---|---|---|
| `lscr.io/linuxserver/sonarr:4.0.15` | 1.3 s | 4.0.19 |
| `qmcgaw/gluetun:v3.40.0` | 0.9 s | v3.41.3 |
| `ghcr.io/autobrr/autobrr:v1.80.0` | 2.1 s | v1.85.0 |

### Compare versions, not strings

`4.9.5` comes **before** `4.16.1`, which alphabetical sorting reverses. Tags are converted
into tuples of integers, and only those following the same convention are compared — one
repository mixes `v1.85.0`, `1.85`, `version-1.85.0` and `latest`.

### The bug that made the page mute

A badly escaped newline in the Python source ended up **in the middle of a JavaScript
string**. The string was unterminated: the whole script died, the page loaded normally, and
nothing updated any more — neither the status nor the versions.

A test now checks that no string in the served script crosses a line.

### Two servers on the same port, silently

`HTTPServer` enables `allow_reuse_address`. On Linux, `SO_REUSEADDR` does not allow two
simultaneous listens; **on Windows it does**: a second `bind` succeeds without a word, and
requests go at random to one process or the other. Each having drawn its own token, the page
answered "invalid token" half the time.

The server now refuses to share its port. Verified: the second start fails with
`WinError 10048`, and only one listener remains.

---

## Recyclarr 8.7.1 — verified on 2026-09-01

Image `ghcr.io/recyclarr/recyclarr:8.7.1`. Recyclarr syncs the TRaSH Guides' quality
profiles and *custom formats* into Sonarr and Radarr. PlugArr reimplements nothing: it asks
Recyclarr to generate its configuration from an **official** template, then writes into it
only the URL and the API key.

### The container has no web UI

It runs on a schedule, `CRON_SCHEDULE=@daily` by default, and `RECYCLARR_CONFIG_DIR=/config`.
Three consequences in the code:

- its `internal_port` is `0` and **no port is published**;
- the preflight does not check its port: the line "port 0: free" taught nothing and made the
  rest of the table look doubtful;
- the access page gives it **no** link. It used to offer one to `http://192.168.1.10:0`,
  right under a note saying "No web UI". A dead link in the middle of a page of shortcuts
  makes people conclude the installation failed.

The entrypoint is `/sbin/tini -- /entrypoint.sh` and takes subcommands directly:
`--version`, not `recyclarr --version`.

### `config create` ignores `--path`

`config create --template X --template Y` writes **one file per template** into
`/config/configs/X.yml`, whatever `--path` says. Recyclarr then loads the whole folder.
Generation is therefore done through `docker compose run --rm --no-deps`, a throwaway
container: the configuration exists before the scheduled service has run even once.

22 official Sonarr templates, 25 Radarr ones, including French profiles
(`french-multi-vf-hd-bluray-web`). The list is read from disk, from the resources Recyclarr
clones on first start — not copied into the code, where it would go stale.

### The templates carry plaintext markers

```yaml
sonarr:
  web-1080p:
    base_url: Put your Sonarr URL here
    api_key: Put your API key here
```

Those are the only two lines PlugArr replaces. Everything else comes from the guide and must
stay intact — that is the module's central guarantee.

### Two defects found by the tests, not by reading

**`\s` also matches the newline.** The pattern ended with `\s*$`: greedy, it swallowed the
blank lines that followed the marker. The file stayed valid and the sync succeeded, but
PlugArr was reformatting, along the way, a file it had committed not to touch. The patterns
are now bounded to **horizontal** whitespace, `[^\S\n]`.

Verified across the **47 official templates**: each is filled in, no other line modified, no
line lost.

**A replacement string is not text.** `re.sub` interprets backslashes in the replacement. A
hand-typed `url_base` containing one would have raised `bad escape` instead of writing the
file. The replacement now goes through a function.

### A filename is not an identifier

First version: list `official/<service>/templates/*.yml` and offer the filenames. Wrong, and
on two counts at once.

It is `templates.json`, at the root of the cloned repository, that is authoritative. It maps
each file to the `id` that `config create --template` accepts, and the two often differ:

| File | Identifier |
|---|---|
| `sonarr/templates/german-hd-bluray-web.yml` | `sonarr-german-hd-bluray-web` |
| `radarr/templates/german-hd-bluray-web.yml` | `radarr-german-hd-bluray-web` |

11 of the 22 Sonarr templates and 11 of the 35 Radarr ones carry that prefix — it resolves
the ambiguity between two identically named files. The glob would therefore have offered
names Recyclarr refuses. It also missed the **10 templates filed under
`radarr/templates/sqp/`**, which a `glob("*.yml")` does not see: 25 found instead of 35.

`scripts/audit_templates.py` checks both default names against the published manifest and
exits non-zero if one of them disappears.

### The manifest is readable without downloading the image

The container's first start clones the template repositories: **59 seconds**, measured.
Imposing that before the wizard's summary would be absurd.

`https://raw.githubusercontent.com/recyclarr/config-templates/master/templates.json` answers
in 0.3 s, and its content is **byte-for-byte identical** (sha256 compared) to what Recyclarr
clones. The wizard therefore reads the disk when Recyclarr has already run — that is what
this particular installation knows — and queries the repository otherwise. Without network
access, the names remain typeable, simply unverified: not being able to list is no reason to
stop someone who knows what they want.

Verified end to end with a French profile: `french-multi-vf-hd-bluray-web` → 57 custom
formats and the profile `[French MULTi.VF] HD Bluray + WEB` created in Radarr.

### Recyclarr refuses to overwrite, and `wire` must stay idempotent

`config create` stops on `The file /config/configs/hd-bluray-web.yml already exists`. The
refusal is legitimate: the file may have been edited by hand. But `plugarr wire` is
documented as replayable, and so it failed on the second pass.

PlugArr now only asks for the **missing** templates. `--force` exists, but using it would
destroy the user's settings on every wiring run.

Corollary when reading the result: a file already filled in no longer has a marker to
replace. That is not a failure, it is a second pass. Only a *remaining* marker is a problem.
Verified: three `wire` runs in a row, all `OK`, a single call to `config create`.

### The target service is read from the YAML, not from the filename

`hd-bluray-web` is a template title, not a service name. Trusting the filename would send
Radarr's key into a Sonarr file. The YAML's root key is authoritative.

A file left behind by a previous installation — the user had Radarr and then removed it —
keeps its markers and makes `recyclarr sync` fail with an obscure message. PlugArr names it
at the end of the wiring.

### Result, confirmed by Sonarr and Radarr themselves

Installing `sonarr,radarr,recyclarr` then running `recyclarr sync`:

| Check | Sonarr | Radarr |
|---|---|---|
| Custom formats created | 37 | 40 |
| Quality sizes synced | 14 | 14 |
| Profile created | `WEB-1080p` | `HD Bluray + WEB` |
| Formats **scored** in that profile | 37 | 25 |

The numbers come from `GET /api/v3/qualityprofile` and `GET /api/v3/customformat` queried
with each instance's key, not from Recyclarr's logs. A profile whose formats were all at
zero would sort nothing: the score is what counts, and it is there.

### Update detection on ghcr.io

The repository is not on Docker Hub: the generic registry v2 route applies. It answers in
~1 s. Verified both ways, since otherwise "no update" proves nothing:

- `8.7.1` → nothing newer (it really is the latest);
- `7.4.1` → offers `8.6.0`, `8.7.0`, `8.7.1`.

---

## Docker Desktop on Windows — verified on 2026-09-01

The README points Windows users at Docker. What remained to be known was whether the
project's central promise — **the single `/data` mount that makes hardlinks possible** —
holds through a Docker Desktop bind mount. It had only been verified on native Linux.

It holds. In a container mounting a Windows path (`-v C:/tmp/hltest:/data`):

```
/data/torrents/film.mkv : 2 links, inode 1970324838307120
/data/media/film.mkv    : 2 links, inode 1970324838307120
```

Same inode, and a write through either name is visible through the other: it is a real link,
not a copy. An *arr import will therefore not copy 40 GB.

One caveat, cosmetic: on the Windows side, the **size** shown for the second name may lag
(17 bytes against 23) while the content read is indeed the same. That is Docker Desktop's
file translation layer, not the link.

### The packaging holds too

Installation from GitHub into a fresh environment, as a stranger would do: `app.tcss` is
properly embedded in the package, the wizard starts and its stylesheet is loaded. Without
that artefact declared in `pyproject.toml`, the wizard would open with no styling at all for
every user.

The README said `pipx install plugarr`. The package is not on PyPI (HTTP 404): the command
failed for everyone. Fixed to `pipx install git+https://…`.

---

## qui v1.27.0 and the complete wiring — verified on 2026-09-01

An installation of the **entire catalogue** (11 services) on Docker Desktop, followed by a
service-by-service verification through their APIs. It found two links that were missing or
wrong even though the report announced them as done.

### autobrr could not reach Transmission

The report showed **19/20**. The cause:

```
error getting rpc info: http://transmission:9091: can't get session values:
'session-get' rpc method failed: can't unmarshal request answer body: invalid cha…
```

Transmission does not expose its RPC at the root. Measured from the stack's network:

| Address | Response |
|---|---|
| `http://transmission:9091/` | **301**, HTML body |
| `http://transmission:9091/transmission/rpc` | **409** — the normal answer, "I need a session token" |

autobrr expects JSON and chokes on the HTML's `<`. Confirmed against its own test endpoint:
root → **HTTP 500**, `/transmission/rpc` → **HTTP 204**.

The *arr do not have that problem: their download client template carries a separate
`urlBase` field, filled in on its own.

### qui was installed without being connected

More annoying, because invisible in the report: `qui` was deployed with a plain
`depends_on: qbittorrent` and **no connection at all**. The user would open a UI that asked
them again for the address and the credentials PlugArr had just generated. Flood, by
contrast, did get its `--qburl` and its credentials at startup.

Four findings on the instance, none of them guessable:

- **everything answers 428** as long as the first account does not exist, including the login
  page. That is the "installation to be completed" signal, not a failure;
- the entry point for creating it is `POST /api/auth/setup`, and it answers
  **400 "Setup already completed"** once played. That is what makes the step replayable;
- an instance is declared with its **full URL**. Passing `host` and `port` separately is
  accepted with a reassuring 201, but the port is lost: qui records `http://qbittorrent` and
  never connects. Verified in both cases:

  | Shape sent | Recorded | `connected` | `GET /torrents` |
  |---|---|---|---|
  | `host` + `port` | `http://qbittorrent` | **false** | 500 |
  | full URL | `http://qbittorrent:8080` | **true** | 200 |

- **duplicates are not refused.** Declaring the same instance twice gives two entries.
  Without a prior check, every `plugarr wire` would add one.

`GET /api/instances` exposes `connected` and `connectionStatus`: the link is therefore
validated by qui itself, the way the *arr are validated by their *Test* button.

### Recyclarr syncs from installation time

The configuration was written but the sync waited for the daily schedule. Right after the
installation, Sonarr had no TRaSH profile: anyone going to check concluded nothing had
worked. The wiring now starts the first sync and announces the profiles created, read from
Recyclarr's output.

A failure of that sync remains a **warning**, not a failure: the files are written and the
schedule will try again. Failing the wiring would show "20/21 links" when all twenty-one are
in place.

### Result: 21/21, and 27 independent verifications

| Link | Verified by |
|---|---|
| Prowlarr → Sonarr, Radarr, Lidarr | `syncLevel=fullSync` in `/api/v1/applications` |
| Prowlarr → Transmission, qBittorrent | `/api/v1/downloadclient` |
| Sonarr, Radarr, Lidarr → both clients | `enable=true` in `/downloadclient` |
| Sonarr, Radarr, Lidarr → root folder | `/rootfolder` |
| Sonarr, Radarr → Jellyfin | `/notification` |
| Recyclarr → Sonarr, Radarr | profiles and custom formats in `/qualityprofile` |
| autobrr → 5 services | `/api/download_clients` |
| qui → qBittorrent | `connected: true` |
| Jellyfin | three libraries in `/Library/VirtualFolders` |
| Flood → qBittorrent | container startup arguments |

A trap for anyone redoing this verification: **Lidarr exposes `v1`**, not `v3`. My first
script queried it on v3, got 404 and reported three false failures. `catalog.py` had been
right all along.

---

## Prowlarr left its UI unreachable — fixed on 2026-09-01

Reported by a user: "I tried to log into Prowlarr, incorrect credentials". The report did
announce a username and a password, though, and the wiring showed all its links green.

### What was happening

The pre-seeding writes `<Username>`, `<Password>` and `<PasswordConfirmation>` into
`config.xml`. Sonarr 4.0.19, Radarr 6.3.0 and Lidarr 3.1.0 consume them on first start,
create the account in their database, then erase those lines from the file.

**Prowlarr 2.5.2 erases them too — without creating anyone.** Reproduced on a throwaway
container, fresh configuration:

| | `Users` in the database | `POST /login` |
|---|---|---|
| Sonarr, Radarr, Lidarr | `[('plugarr', …)]` | 302 to `/` |
| Prowlarr | **`[]`** | 302 to `/login?loginFailed=true` |

And its login page offers **no account creation**. With `AuthenticationRequired=Enabled`, the
UI therefore became permanently unreachable.

The worst part: nothing said so. The wiring goes through the API key, which worked
perfectly. The twenty-one links really were in place. The only way to see the failure was to
try logging in — which no verification did.

### The fix

One wiring step per *arr, which **posts the login form like a browser**. A success redirects
to the root, a failure to `/login?...loginFailed=true`.

If the login fails, the account is created through the supported route:
`PUT /api/v1/config/host/{id}` with `username`, `password` and `passwordConfirmation` — the
application hashes the password itself. Verified: **202**, the row appears in `Users` with
its 10,000 iterations, and the login succeeds.

If it already works, **nothing is written**: rewriting a correct password would be a change
for nothing.

On a fresh six-service installation:

```
OK sonarr: acces web - connexion verifiee
OK radarr: acces web - connexion verifiee
OK lidarr: acces web - connexion verifiee
OK prowlarr: acces web - compte cree
```

The four announced sets of credentials then really do open their UI.

### What this episode says about the method

The project's rule is to have every link validated by the target application. It was applied
to links between services, not to the user's own access. A verification that does not take
the user's path proves nothing about that path.

---

## Passwords: special characters — verified on 2026-09-01

Requested from use: random passwords of at least 12 characters, mixing letters, digits and
special characters.

They were already random — `secrets.choice`, 20 characters, different for every installation
— but **alphanumeric only**.

### Why the special alphabet is short

These values travel through a `.env` read by Docker Compose, a container command line, an
XML file, an INI file and several JSON payloads. The danger was measured, not assumed:

```
.env:          PASS_NU=abc$HOME!def
compose sees:  abcC:\Users\darkl!def
```

Compose reads `$` as variable interpolation **inside the `.env` file itself**. A password
containing one would arrive mangled inside the container, and the user could never log in.

Excluded, therefore: `$`, the apostrophe (it would close the value), the double quote, the
backslash, the backtick, `#`, and every shell metacharacter — the `.env` is sometimes sourced
by a script, including in this repository's CI.

That leaves 13 special characters, so 75 possible in total: roughly **125 bits** of entropy
across 20 positions.

`.env` values are now written between single quotes. Verified: a quoted value containing `$`
arrives **intact** in the container, where the same bare value was interpolated. Paths are
quoted the same way — for consistency, not out of necessity: a path containing a space
already worked.

### The verification that counts: the worst case

A random draw would probably have worked. So a ten-service installation was performed with,
for **every** account, the most hostile password possible:

```
Aa1!@%^*-_=+.,:?zZ9
```

24 links out of 24, then twelve independent verifications:

| Check | Result |
|---|---|
| `.env` quoted and readable back | exact value |
| `docker compose config` | valid |
| Sonarr, Radarr, Lidarr, Prowlarr | web login, redirect to `/` |
| qBittorrent | HTTP 204 + session cookie |
| Transmission | RPC authentication, HTTP 200 |
| autobrr, qui | HTTP 204 / 200 |
| Jellyfin | HTTP 200 |
| Flood | password passed intact as an argument |

Only one line failed at first: qBittorrent's. It was **the test that was wrong**. The old API
answered `200 Ok.`; 5.2.3 answers **204** and sets a `SID` cookie, and refuses with a
**401**. The stored PBKDF2 hash did match the password, recomputation to prove it.

### Existing installations do not change

The passwords live in `stack.yml`. An already installed stack keeps its own: only new
installations get the new alphabet.

---

## Windows executable — verified on 2026-09-01

Goal: remove the last prerequisite a Windows user had, installing Python. PyInstaller
6.22.2, a single file, console mode.

### Three obstacles, none of them guessable

**The obvious entry point does not work.** `src/plugarr/__main__.py` does a relative import
(`from .cli import app`), and PyInstaller runs its entry script as a top-level module, with
no parent package:

```
ImportError: attempted relative import with no known parent package
```

Hence `packaging/launcher.py`, which does nothing but an absolute import.

**`app.tcss` has to be embedded explicitly.** Without it, Textual raises `StylesheetError` at
startup and the wizard does not open. Verified by deliberately building without the file: the
executable stops, exit code 1.

**The `--add-data` path is relative to the `.spec` file**, not to the current directory. With
`--specpath`, a relative path makes the build fail on a confusing
`Unable to find … when adding binary and data files`.

### What was verified on the produced binary

| Check | Result |
|---|---|
| Catalogue, help, template list (network) | correct |
| Docker preflight | daemon and compose detected |
| Textual wizard | **137 style rules**, 11 services shown |
| Full installation | **14/14 links**, 168 seconds |
| Self-containment | works with an emptied `PATH` and an invalid `PYTHONHOME` |
| Size and startup | 20.5 MB, ~1.5 s |

### What is published, and how

`.github/workflows/windows-exe.yml` builds the binary on `windows-latest` on every push,
checks it, then attaches it to the release on a `v*` tag.

The check does not merely verify that the file exists: it builds a second, throwaway
executable from `packaging/smoke_tui.py`, which really starts the wizard and counts the style
rules loaded. That is the only way to catch a forgotten stylesheet, a failure invisible until
somebody runs the binary.

The binary is not signed. Windows SmartScreen will therefore show a warning on first launch,
which the README announces rather than letting it come as a surprise.

---

## Windows had no profile — fixed on 2026-09-01

Reported from use, with a screenshot: the wizard, launched from the executable on Windows,
only offered `generic-linux`, `unraid` and `synology`. The user had picked **unraid**, and so
ended up with `/mnt/user/appdata/plugarr` and `/mnt/user/data` on a Windows machine.

### What those paths did

Nothing visible, and that is the problem. Docker Desktop creates them at the root of the
current drive: `/mnt/user/data` becomes `C:\mnt\user\data`. The installation succeeds, the
containers start, and the files land in a folder nobody wanted.

The *Check the paths* button even answered "hardlink OK" — technically true, since it had just
created that parasite folder.

### Three fixes

**A `windows` profile**, with `C:/plugarr/config` and `C:/plugarr/data`. The preselected
profile is now the machine's own, in the wizard as on the command line (`--platform` takes the
same default).

**PUID/PGID explained.** "1000:1000" means nothing to someone who has never administered a
Unix system, and yet that value decides who will own the downloaded files. A line now says so.
On the Windows profile, the yellow "not detectable" warning disappears: under Docker Desktop
those ids have no effect, and writing it worried people for nothing.

**The check says where the folder lands.** It shows the resolved path, and flags a path
inconsistent with the machine:

```
« /mnt/user/data » n'est pas un chemin Windows. Il sera cree dans
C:\mnt\user\data, ce qui n'est probablement pas voulu.
```

### A defect found by the tests

The first version of that check used a character class in which `\/` only means the forward
slash: the faulty form recognised **no** backslash path at all, not even `C:\Users\...`, and
flagged them all as "not a Windows path". Two tests caught it before any release.

---

## Reinstalling over an existing configuration — fixed on 2026-09-01

Reported from use, with a screenshot: an installation re-run over an already used
`config_root` gave 19 links out of 25, with incomprehensible messages — "unreadable response
on the categories", "HTTP 401", "autobrr's API may have changed shape", "qui never became
available".

One single root cause, and four defects it revealed.

### The cause: passwords announced but never applied

The configuration folders dated from the previous day, the installation was an hour old.
PlugArr kept the existing configurations **but generated new passwords**, which it displayed
in its report. The services therefore rejected the credentials shown to the user. Verified:
the PBKDF2 hash stored in `qBittorrent.conf` did not match the password in `stack.yml`.

qBittorrent and Transmission are now **realigned**: only the two credential lines are
rewritten, the rest of the file belongs to the user.

### Writing while a container is running achieves nothing

qBittorrent keeps its configuration in memory, and Transmission **rewrites its
`settings.json` as it stops** — our correction would have been erased minutes later. The
installation therefore stops the existing containers *before* pre-seeding.

### The preflight refused our own ports

A running stack occupies its ports. The preflight declared them "already in use" and blocked
— that is to say, exactly the most common case, reinstalling after a first attempt. Ports
published by the current project are now recognised as its own.

### qBittorrent's address ban

After five authentication failures, qBittorrent bans the address for an hour. An installation
that got the password wrong therefore gets Sonarr's address banned. What follows is cruel: the
password becomes correct again, but the *arr gets a 403 and answers "Authentication Failure",
blaming the credentials.

Measured at the same moment, with the same password:

| From | Response |
|---|---|
| the host | **204** |
| the Sonarr container | **403** |

The threshold is raised to 100 in the seeded configuration — brute-force protection is still
useful, it simply must not target our own containers.

A repair remains as a fallback (restart then retry), **strictly limited to authentication
refusals**. Broadening it to any test failure manufactured the next failure: the restart
invalidated the address Sonarr had cached, which then failed on "Unable to connect". The
remedy created the symptom.

### What stays impossible, and is now said

Jellyfin, autobrr and qui only store their password **hashed**, and no API allows resetting it
without it. PlugArr therefore cannot take those three services over. The preflight announces
it before starting, and every failure now carries the useful sentence: delete this folder, or
resume the original installation with `--project-dir`.

### Result

| Scenario | Before | After |
|---|---|---|
| Fresh installation, 8 services | — | **19/19** |
| Reinstallation, same folders | 19/25 | every download client wired, only the three hashed-password services refuse, with the explanation |

### A crash, too

Entering a tracker then clicking *Add* closed the window. `add` protected its HTTP call, but
not `configured()` or `app_profile_id()`, which query Prowlarr as well: an exception inside a
Textual worker stops the application, and the user loses their input **and** the explanation.
The wizard's four workers are now sealed, and the traceback goes to the log.

---

## Three user requests — 2026-09-01

### "Ask whether to keep or to delete"

Detecting an inherited configuration only served to show a warning. The wizard now offers the
choice, and the command line asks the question (`--reset-config` / `--keep-config` to answer
it in advance).

With no explicit answer, **we keep**: erasing somebody's configuration by default would be
unacceptable. `--yes` answers questions, not deletions.

The deletion is bounded by three locks, written to be readable at a glance: only catalogue
services are accepted, the folder must sit under `config_root` **after resolving symbolic
links**, and `data_root` is never walked. A test creates a link pointing outside the root and
verifies that the deletion is refused, the targeted file still there.

### "A menu with clickable choices"

The quality profiles screen asked you to **type** a name, while showing only six out of
twenty-two. Nobody can guess the other sixteen.

A clickable dropdown replaces it, filled from the manifest: 22 profiles for Sonarr, 35 for
Radarr. The name check stays, but it can no longer be triggered by a typo.

### "Open the HTML page automatically at the end"

The command line already did; the wizard settled for a button. Yet that is where the page is
useful: it carries the addresses and the credentials that were just announced. It now opens on
its own, and the button remains for machines with no browser — a command-line NAS, for
instance.

Two safeguards: nothing opens if the file does not exist, and both the screenshot generator
and the tests disable the opening. Launching a browser during CI would make no sense.

---

## The username is a choice — 2026-09-01

Requested from use: "not everyone wants to put PlugArr as their username".

A single place in the code fixed that name; everything else was only a fallback. It is now
carried by `StackConfig`, exposed through `--username` and a wizard field, and it reaches all
five service families.

### The format constraint, and what it is really worth

First version: a three-character minimum, "because qBittorrent requires it". **That was
false.** Verified on qBittorrent 5.2.3 with a configuration seeded for the username `ab`: the
login answers **204**. The rule was brought down to one character, and the comment corrected.

What does remain constrained is constrained for a real reason: this name ends up in an XML
file, an INI file, JSON, a login form and a container command line. Spaces, accents and exotic
punctuation might get through — but "might" is not good enough for a value you cannot change
without reinstalling everything. Hence `[A-Za-z0-9._-]{1,32}`.

### Verified on a real installation

`--username yannick`, six services, 17 links out of 17, then a login to each with that name:

| Service | Login |
|---|---|
| Prowlarr, Sonarr, Radarr | redirect to `/` |
| qBittorrent | HTTP 204 |
| Transmission | RPC 200 |
| Jellyfin | HTTP 200 |

---

## The frozen page and the pinned versions — 2026-09-01

Two usage remarks on the same day: "when I connected to qui, I did not have the latest
version", and "the page does not tell me whether there is an update, and does not let me stop
or restart an instance".

### The catalogue ages, and that has to be measured

Every catalogue tag was checked against its registry. Ten services out of eleven were up to
date; **`qui` was one version behind**, v1.27.0 against v1.28.0.

The new version was verified before being pinned, as the project's rule requires: 428 before
the account is created, 201 on `POST /api/auth/setup`, 200 on login, 201 on the instance
declaration, correct read-back. Identical behaviour.

The full check fits in one command and is worth replaying before every release:

```
for sid in catalog.STARTUP_ORDER: updates.newer_tags(catalog.get(sid).image)
```

### "The page does not let me stop an instance"

That was accurate, and intended: the access page is a frozen file, with no server behind it.
Service status, the buttons and the updates come from `plugarr serve`.

The defect was therefore not in the page, but in the route to get there. It displayed "run
`plugarr serve`" — a useless command for someone who has just double-clicked an executable
that is not on their PATH.

An `administration.cmd` launcher (`administration.sh` elsewhere) is now written next to the
artefacts. It carries the real path of the executable used for this installation, and a
`--project-dir` pointing at the right folder — without which `serve` would look for a
`stack.yml` wherever the double-click happened.

Verified by launching it as a double-click would: the admin page answers, HTTP 401 with no
token, which is exactly the expected behaviour.
