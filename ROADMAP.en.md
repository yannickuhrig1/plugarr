*[Français](ROADMAP.md) · **English***

# Roadmap

Where PlugArr stands, what comes next, and why. Kept up to date after every
working session.

**Last updated: 7 September 2026** — published version: **0.7.3**

---

## What works today

Sixteen services installed and **wired** in one pass, verified against real
instances at every release.

| | |
|---|---|
| **Download** | Transmission, qBittorrent, **SABnzbd** *(Usenet)* |
| **Library** | Sonarr, Radarr, Lidarr |
| **Indexers** | Prowlarr |
| **Media** | Jellyfin, Silo *(experimental)* |
| **Books** | Audiobookshelf |
| **Music** | DroppedNeedle *(replaces Lidarr)* |
| **Requests** | Seerr |
| **Automation** | autobrr, Recyclarr |
| **UIs** | Flood, qui |
| **Network** | Gluetun *(optional VPN)* |

The wizard covers **every** command line option: a test compares the signature
of `install` against what the wizard can set, and fails if a gap appears.

**PlugArr speaks French and English**, and the two languages at play no longer
get confused. PlugArr's own — wizard, command line, report, access page — is
chosen on the welcome screen or through `--lang`, and starts from the system's:
a French speaker finds it in French without setting anything, everyone else in
English. The **services'** language is asked separately, on the paths screen,
and applies to every application that can take it. You may want the tool in
English and your media library in French.

A phrase added in French and forgotten in the catalogue breaks nothing: it
would simply show up in French to someone who asked for English, with no error
and no warning. `scripts/audit_traductions.py` therefore collects all 540
displayable phrases and **fails if one is missing**, or if the catalogue holds a
dead entry. It runs in CI.

**Eight libraries** are created and organised: movies, shows, **anime**, music,
live performances, books, audiobooks and software. Each has its download folder,
its media folder and its qBittorrent category sending one to the other. Sonarr
gets a separate root folder for anime, as the TRaSH Guides recommend. Books and
audiobooks are now driven by Audiobookshelf; live performances and software still
hold manual downloads, waiting for Shelfarr, Shelfmark and the others.

**The whole configuration can be backed up and restored.** `plugarr backup`
archives the project directory, `CONFIG_ROOT` and **the Docker volumes** — Silo's
database is not under `CONFIG_ROOT`, and a backup that only archives folders
would miss it silently. Containers are stopped during the copy: a SQLite database
copied hot gives a file that looks valid and is unusable in practice. `DATA_ROOT`
is never touched. `plugarr restore` puts everything back, including somewhere
else, rewriting the paths. **Both directions also live in the wizard**, on its
first screen: that is the only place someone who double-clicks the executable
ever sees, and the installation to archive is found there on its own.

qBittorrent's **RSS reader** is enabled, automatic downloading included. PlugArr
adds neither feed nor rule: they depend on your trackers, exactly like the
indexers.

**An older installation catches up in one command.** `plugarr upgrade` migrates
`stack.yml` if its schema changed, brings the images in line with this
version's catalogue — **never moving backwards** from a version you chose
yourself — regenerates the artefacts, then replays the wiring.

The admin page (`plugarr serve`) gives the status of the services, starts them,
stops them, restarts them, reports available updates and applies them, shows the
credentials, **rotates a password or an API key while re-wiring everything that
depends on it**, and **installs a service missing from the initial
installation**.

---

## Digests recorded for the services to come

Verified against the registries on 4 September 2026, ready to be pinned. This is
not the work, it is its precondition: a service only enters the catalogue once it
is **wired and verified** against a real instance. Three of the five digests
recorded that day are now in the catalogue: Seerr, Audiobookshelf and
DroppedNeedle.

| | pinned image |
|---|---|
| Shelfarr | `ghcr.io/pedro-revez-silva/shelfarr:2026.08.31.1@sha256:08e06f5b…` |
| Shelfmark | `ghcr.io/calibrain/shelfmark:v1.3.15@sha256:96022903…` |

---

## Next up

**Shelfarr and Shelfmark**, the last two services on the list. Their digests are
already recorded, and Audiobookshelf unblocks them: they deliver into its
libraries.

### What the pack update settled — shipped in 0.6.0

`stack.yml` had carried a `version: 1` field since the project's first line, and
**nothing read it**. That was not a matter of hygiene: pydantic ignores fields it
does not know, so an older version reading a newer `stack.yml` threw part of it
away — and the **first write destroyed it**, since `install`, `generate` and
password rotation all rewrite that file.

The loss was reproduced before being fixed:

    version read           : 2
    future field kept?     : False
    future field written?  : False

| | |
|---|---|
| `stack.yml` migrations, keyed on its version number | ✅ 0.6.0 |
| Apply a new catalogue's pinned digests to an older installation | ✅ 0.6.0 |
| Replay the wiring steps that changed since the installed version | ✅ through `wire`, see below |

**The third point did not ask for what it announced.** Keeping a register of
"steps that changed since version X" meant versioning every wiring step and
maintaining that table on every change — to gain nothing but execution time,
since `wire` is **idempotent** by construction and an already-applied step
simply reads itself back. So `upgrade` replays everything, and says so.

**No encrypted secrets file**, and the reason is mechanical rather than
philosophical: it is **Docker Compose** that reads the `.env`, not plugarr.
`POSTGRES_PASSWORD`, `SILO_SECRET_KEY` and the VPN credentials must be in
cleartext on disk at `up` time, or the stack does not start. Encrypting
`stack.yml` while `.env` sits in the clear next to it would be decorative. Real
encryption implies a passphrase typed at every start, which removes the automatic
startup shipped in 0.1.9. What protects you today: `chmod 600`, a generated
`.gitignore`, and secret masking in the log.

---

## Delivered recently

| | Status | Note |
|---|---|---|
| **Password rotation** | ✅ shipped in 0.1.7 | qBittorrent, Transmission and the *arr. Verified on an eleven-service stack: 25 links out of 25 realigned. |
| **API key rotation** | ✅ shipped in 0.1.8 | On the *arr. Trap verified against Sonarr 4.0.19: `PUT config/host` answers **202 Accepted** and changes nothing — the key read back is still the old one a minute later. Only rewriting `config.xml` followed by a restart works. |
| **Adding a service afterwards** | ✅ shipped in 0.1.8 | "Add a service" section on the admin page. Verified for real: a Sonarr-only stack, then Prowlarr added — 4 links wired, Sonarr's key and password untouched. |
| **Silo** | ✅ shipped in 0.1.11 | Media server with a Jellyfin-compatible API, **marked experimental**. Three containers — `pgvector/pgvector:pg18`, `redis:alpine` and `silo-server`, pinned by digest; Meilisearch is optional and is not installed. Account, **profile** and three libraries created and read back. Two traps measured, not assumed: its database must live in a **Docker volume** (host mount: migrations in **2935 s** against **5 s**), and its database password must be alphanumeric — one `?` in a `postgres://` and the container restarts in a loop. |
| **UI language** | ✅ shipped in 0.1.11 | Asked once in the wizard, applied everywhere. Every application expresses the same idea differently: Sonarr and Radarr want an integer, **Prowlarr wants the code** (`fr`), Jellyfin a culture and a country, Silo a code **per library**. The table of the *arr's 29 languages is published nowhere: recorded value by value against a Sonarr 4.0.19. An inconsistency was fixed along the way — PlugArr forced French on Jellyfin, hardcoded, and left everything else in English. |
| **VPN country list** | ✅ shipped in 0.1.8 | Clickable list, extracted from the **pinned** image. Trap found along the way: five providers expose no country — four classify by region, one by city. `SERVER_COUNTRIES` filtered nothing for them. |

---

## Services to come

A service only enters the catalogue once it is **wired and verified** against a
real instance. The order below is the order of study.

| | What is left to do |
|---|---|
| **Plex** | A second media server. Its token comes from `plex.tv`, not from the local API: that is the point to verify before adding it. |
| **Notifiarr** | Centralised notifications. Every *arr registers with an API key. |
| **Bazarr** | Subtitles. Its configuration goes through a YAML file rather than an API — nothing verified yet. |
| **Wizarr** | Invitations and account management for Jellyfin, Plex and Emby. The most self-contained on the list: one container, and the wiring boils down to the media server and its key. |
| **Tautulli** | **Plex** monitoring and statistics. Cannot come before Plex. |
| **Jellystat** | Jellyfin statistics. Requires a **PostgreSQL** database in a second container, where the whole catalogue fits in one. |
| **Tracearr** | Playback tracking and account sharing detection. The `latest` image demands an external database and Redis; the `supervised` tag bundles everything into one container. |
| **Shelfarr** | `ghcr.io/pedro-revez-silva/shelfarr`, **2026.08.31.1**. Book requests for the *arr ecosystem — a Seerr for books. Searches through Prowlarr, downloads via qBittorrent, delivers to Audiobookshelf. Fills the hole left by Readarr, archived since 27 June 2025. |
| **Shelfmark** | `ghcr.io/calibrain/shelfmark`, **v1.3.15**, 60 releases. A search and request UI for books, with sources and clients brought by you. |

**Readarr is not on the list**: the project has been archived since 27 June 2025.

### Distribution to study

- [ ] **Proxmox VE Helper-Scripts / Community Scripts** — Study adding PlugArr to the
  Proxmox community script catalogue to make it easier to install. Check the admission
  criteria, the right deployment mode and the script's maintenance before proposing
  anything.


---

## The PlugArr console

The only piece of work that is not simply another service. Today the wizard
installs and then steps aside; `plugarr serve` fills part of the gap, but remains
a command you have to launch.

| | Status |
|---|---|
| Service status | ✅ |
| Start, stop, restart | ✅ |
| See and apply updates | ✅ |
| Run the diagnostic | ✅ 0.1.11 |
| Force an update check | ✅ 0.1.11 |
| Rotate a password, with re-wiring | ✅ |
| Rotate an API key, with re-wiring | ✅ |
| Add a service missing from the installation | ✅ |
| Automatic startup, without launching a command | ✅ 0.1.9 |

**Why not a container.** The question was settled by measuring it. The console
has to create, start and recreate containers, which means `POST
/containers/create` then `/start` in the Docker API. But a container you create
can mount the host's root and run as root: a socket proxy that allows those two
calls locks nothing away, and without them the console is useless. Locking it
inside one would therefore mean exposing an all-powerful service on the network
for nothing in return.

So it runs on the host, under the user's account, on `127.0.0.1`, and starts on
its own with `plugarr autostart`. The convenience sought is the same. And because
a console that changes passwords must authenticate itself seriously, `plugarr
admin-password` sets a password: hash only in `stack.yml`, expiring sessions,
rate-limited attempts.

---

## What will not be done

**Choosing several Recyclarr profiles per service.** Recyclarr groups its
instances by `base_url` and **discards any group holding more than one** — that
is `SplitInstancesFilter`, read in its source code. Two profiles targeting the
same Sonarr, and it is not two profiles that get applied: it is **zero**. Root
templates are self-contained and do not compose; the only way through would be to
merge their YAML ourselves, exactly what this project refuses — the whole point is
that the content comes from the TRaSH Guides and not from us.

PlugArr now detects that situation and keeps only one, renaming the others rather
than deleting them.

---

## Log of notable fixes

| Version | |
|---|---|
| **0.7.3** | **The `stack.yml` history was four times too short.** Five versions looked like they covered "a run of quick retries"; one real install of five services consumed FOUR on its own. `write_artifacts` is called three times by `install` — before seeding, after adopting the API keys, after wiring — then once more by `wire`. At five entries, two failed installs in a row pushed out the password that did work, which is exactly what this history exists to prevent. Raised to twelve, three full installs. The test locks the ratio between the two. |
| **0.7.3** | **The hashed-password warning contradicted itself two lines later.** PlugArr announced "Credentials kept: jellyfin, qbittorrent", then "their passwords cannot be read back: the ones it is about to announce will be refused". Both cannot be true, and the second offered to DELETE the configuration of services that were working — a dead loss to fix a problem that did not exist. The check now only looks at services whose credentials were NOT reused. Found by running a real reinstall on a five-service stack, in a Proxmox LXC. |
| **0.7.3** | A language test returned a different verdict depending on the machine. `test_la_langue_par_defaut_vient_du_systeme` replaced the environment variables but let `locale.getlocale()` answer whatever it liked: the `de_DE` case passed on a French box and failed on an English one. CI never saw it, its locale being empty. The machine locale is now simulated like everything else, and two more cases state what is expected of an English system and of a French one. |
| **0.7.3** | The "--vpn without a download client" warning lived under `if reprendre:` instead of `if vpn:`. It therefore fired on EVERY reinstall without a download client, talking about an option nobody had passed — and stayed silent in the only case where it helps, since `--repartir-de-zero` skipped the whole block. **Found by running the built executable**, not by re-reading the code. The test checks the structure of the function, not the wording of the message. |
| **0.7.3** | **PlugArr was destroying the only plaintext copy of its own passwords.** Seen on a real machine: Jellyfin account created on 4 September, `stack.yml` rewritten over the following days, and no way left to get into Jellyfin. Jellyfin, autobrr and qui store their password HASHED only — neither readable back nor resettable without it. It therefore existed in exactly one place, and `write_artifacts` overwrote it **three times per install**, one of them before `docker compose up` even ran: a failed install took away the password that did work. `stack.yml` now rotates over five versions, and wiring TRIES the passwords of past installations before reporting a refusal. |
| **0.7.3** | **`stack.yml` was only ever looked for in the current directory.** Anyone launching `plugarr.exe` from their desktop after first running it from `Downloads` started from scratch, silently, with fresh passwords their services then refused. The error message pointed at `--project-dir` — a command-line option, useless to someone who never opens a terminal. A per-user registry, holding ONLY paths, finds the original install wherever it is; the wizard says where it found it and writes its files there, because a Docker stack cannot live in two directories at once. |
| **0.7.3** | **The wizard could restore but not back up.** `plugarr backup` and the admin console had been archiving for a long time; the wizard had not. Yet it is the only thing someone who double-clicks an executable ever sees: they had a backup only if they already had one. The button sits on the first screen, next to "Restore", and the installation to archive is found on its own. Containers are stopped by default: an SQLite database copied live is corrupt without saying so. |
| **0.7.2** | **macOS had no profile at all, and inherited `/srv/data` — which macOS REFUSES to create.** Reported by a user on r/FrancePirate, screenshot included: `[Errno 30] Read-only file system: '/srv'`. Since Catalina the macOS root is a signed system volume, mounted read-only. `default_profile()` only knew `win32` and "everything else": **every** Mac user hit the wall on first run. The `macos` profile puts its paths under the home directory — the only place that is both writable AND shared by default by Docker Desktop. `/opt` would have been worse than `/srv`: writable, so `mkdir` succeeds, but not shared — the failure would only have surfaced at `compose up`. |
| **0.7.2** | **The preflight checked NOWHERE that it could write.** It only tested hardlinks, non-blocking: a fatal condition came out as a yellow warning, on a line about something else, the install went ahead anyway and died on its very first write with a bare errno. Nothing in `OSError : [Errno 30]` says what to change. `check_writable` is **blocking**, covers both roots, actually tries to write rather than trusting `os.access`, and names the remedy. Reproduced before the fix on a read-only tmpfs mount. |
| **0.7.2** | `--dry-run` announced "nothing written yet" and **wrote anyway**. Found while verifying the previous fix. The hardlink check does not guess, it tries — but trying needs two real directories, and it left them behind, along with their whole chain of parents. Yet `--dry-run` is PRECISELY the command you run to look without committing: comparing three locations left three trees behind, and a typo created a directory where the typo was. The cleanup removes only what the test created, and only if it stayed empty. |
| **0.7.2** | A `t()` was missing in `hardlink_supported`, and only one of its three exits: the user's screenshot showed an English table with **one** French line. The translation audit could not see it — it collects the `t("...")` calls present, never an absent one. A test sees it now. |
| **0.7.1** | **PlugArr did not know a newer version of ITSELF existed.** Reported from use: "I have just run 0.6 and it does not detect 0.7". That was right, and the gap was wide open: 0.6.0 shipped `plugarr upgrade`, which aligns the services' IMAGES on the catalogue **of the running binary** — so it assumed the latest binary had already been downloaded, and nothing anywhere said so. `__version__` was only ever displayed. `upgrade`, `doctor` and the console's "check for updates" button now query the latest release, in **one** request. |
| **0.7.1** | **The check is a CONVENIENCE, and behaves like one.** It never raises: PlugArr works perfectly offline, and a NAS behind a firewall must not see an error because it cannot reach GitHub. The nuance that matters: a failure yields "we do not know", **never** "no update" — confusing the two would leave someone on a stale version believing they were current. An exhausted hourly quota gets its own message. |
| **0.7.1** | The message announced "you have 0.7.0" to someone on 0.6.0: `cli` and `autoupdate` each read their own `__version__`. The result now carries the version the comparison was made against, and that is what gets displayed. **Found by reading the message produced**, not by re-reading the code. |
| **0.7.0** | **Reinstalling over an existing installation no longer loses everything.** Asked from use — "it should offer to keep the settings already there". It was worse than "not offered": `install` built its configuration from scratch and **never read the `stack.yml` present**. Measured: username `yannick` -> `plugarr`, Recyclarr profiles emptied, console password lost, and above all **the VPN silently disabled** — the install even displayed "No VPN is configured". Someone reinstalling to fix something else ended up with their torrent traffic in the clear. |
| **0.7.0** | **The carry-over fixes a much older defect.** qBittorrent, Jellyfin, autobrr and the others store their password HASHED only: PlugArr could not read it back, generated a new one, announced it, and the service refused it — that is the failure with incomprehensible messages from 0.1.11. But when PlugArr did the installing, the password is in ITS OWN `stack.yml`, and it never needed to read it elsewhere. Carrying the previous credentials over makes what is announced match what is in place. Hand-shifted ports follow too. |
| **0.7.0** | Carry-over **on by default** — losing a VPN in silence is worse than reusing without asking — but never silent: the summary lists what was carried over, service by service, and a "Start over" choice refuses it. An option given by hand always wins over inheritance, otherwise it would have no effect. `--repartir-de-zero` on the command line. |
| **0.7.0** | **A third exception-hierarchy trap**, after `BadZipFile` in 0.5.2: `yaml.YAMLError` inherits from `Exception`, not from `ValueError`. A corrupt `stack.yml` therefore surfaced the raw error instead of being treated as "unreadable, start fresh". Converted at the source in `migrations.lire`, as the previous time. Found by a test written before the fix. |
| **0.7.0** | **The username has its copy button**, on the access page and the console. Asked from use: it gets copied as much as the password — into a login form, right before it — and it alone had none. It stays displayed in the clear: it is not a secret, the button was what was missing. Verified in a browser, not only in the HTML. |
| **0.6.0** | **`plugarr upgrade`: an older installation catches up in one command.** Until now PlugArr could update ONE service; it could not update **its own installation** when PlugArr itself was what changed. Four steps, in this order because the order matters: migrate `stack.yml`, bring the images in line, regenerate the artefacts, replay the wiring. The wiring comes **last** — a step added since may depend on a newer image, never the other way round. |
| **0.6.0** | **It never moves a version backwards.** The deployed tag lives in `stack.yml` and not in the code, precisely so Sonarr can be updated without waiting for PlugArr, or deliberately held back. So `upgrade` only offers what moves FORWARD, compares numbers rather than strings — `4.9.5` comes before `4.16.1` — and **shows what it sets aside, with the reason**: a service skipped in silence gives the impression everything was aligned. |
| **0.6.0** | **`stack.yml` has always carried a version, and nothing read it.** That was not a matter of hygiene: pydantic ignores fields it does not know, so an older version reading a newer `stack.yml` threw part of it away, and the **first write destroyed it**. The loss was **reproduced before being fixed** — future field written, read back, gone — and PlugArr now refuses to read a file newer than itself rather than reading half of it. Migrations run on the RAW dictionary: after pydantic, "absent" and "default value" are indistinguishable. |
| **0.5.2** | **`plugarr restore` crashed on a file that is not an archive**, exiting on a raw Python traceback followed by "Failed to execute script 'launcher'". `zipfile.BadZipFile` inherits from `Exception`, **not** from `ValueError` or `OSError`: both callers, which caught those two, let it through. The conversion now happens inside `lire_manifeste`, once, rather than in each caller — a third one will benefit too. Found by running the PUBLISHED EXECUTABLE on a text file renamed to `.zip`; every test passed. |
| **0.5.2** | Two messages were still in French and only showed up there: `stack.yml introuvable. Lancez d'abord plugarr install`, and the archive contents table. Same method, same result: run the binary rather than re-read the code. |
| **0.5.1** | **The FAILURE path speaks English too.** 0.5.0 covered the whole happy path; what remained were the messages you only see when something breaks — "qBittorrent never became available", "the pre-seeded config.xml may have been overwritten", "NOT PROTECTED: the tunnel exits on YOUR own public address". They lived in fifteen client modules, `wiring.py`, `vpncheck.py` and the orchestrator, as `WiringError`s raised deep in the code. The catalogue deduplicates them: the same "X never became available" was serving nine call sites. **540 phrases** in total, against 377 in 0.5.0. |
| **0.5.1** | **The files written to disk, too.** `docker-compose.yml`, `.env`, `.gitignore`, `administration.cmd` and the automatic-startup script carried a French header. They are not on-screen messages, but they do get read: you open your `.env` to find a password. Still in French: two HTML templates and one JavaScript block — those are structures, not sentences, and translating them would mean maintaining two copies of a page. |
| **0.5.1** | **A lost plural, caught by a test.** Wrapping "2 deja configures" had dropped the French agreement. Two keys rather than one: French agrees, English does not change, and a single key would have forced one of the two languages to be wrong. |
| **0.5.0** | **PlugArr speaks English**, and two languages stop being confused. PlugArr's own — wizard, command line, report, access page, preflight — is chosen on the welcome screen or through `--lang`, and starts from the system's. The **services'** language is asked separately: you may want the tool in English and your media library in French. The second setting had existed since 0.1.11, but it was **alone**, and therefore ambiguous — the screen said "interface language" without saying whose. The translation key is the French phrase itself: a missing phrase falls back to French, understandable at worst, where a misspelled key would be displayed as-is. |
| **0.5.0** | **The widgets translate in passing.** Wrapping a hundred and fifty phrases by hand would have raised the question on every line written, and a forgotten phrase breaks nothing: it would show in French to someone who asked for English, with no error and no warning. `tui/widgets.py` and `report.py`'s console run their labels through the catalogue; the screens go on writing their phrases in the clear. The safeguard is mechanical: `scripts/audit_traductions.py` collects all **540 displayable phrases** and fails if one is missing, **or** if the catalogue holds a dead entry. It runs in CI, and it already caught one entry added twice. |
| **0.5.0** | **A defect only a real mount could reveal.** `Select` expects `(label, value)` and was getting `(value, label)`: the code `fr` then became illegal, and the wizard died while mounting the welcome screen. Every test passed. |
| **0.5.0** | **The screenshots now exist in both languages**, and the admin console finally has one. It is not a terminal screen — it is HTML served by `plugarr serve` — so `screenshots.py` could not produce it: it was the only visible part of the product with no image at all. `scripts/captures_administration.py` writes the page AND photographs it, with the same precautions as the other captures: illustrative secrets, a fixed address, and a **frozen date** — today's would make the file different on every run. |
| **0.4.0** | **DroppedNeedle enters the catalogue**, unblocked by SABnzbd as expected. It **replaces** Lidarr: music from request to filing. A note in this roadmap claimed its first account was created through the web UI — **that was false**, `POST /api/v1/auth/setup` exists. Two defects found while integrating it, neither visible any other way: its `auth_users` table lives in `/app/cache`, which the upstream compose does not mount, so the setup succeeded and then the login failed after a simple restart; and its SQLite database **refuses to start** on a Windows mount — "The upgraded library database could not be verified". Same remedy as Silo's database. |
| **0.4.0** | **Named Docker volumes are derived from the catalogue.** They were hardcoded in **five places** for Silo's PostgreSQL alone — compose, existing-state detection, reset, location message, backup. The second case made the scattering untenable: a `named_volumes` entry on the service record is now enough, and everything else follows from it. |
| **0.4.0** | **SABnzbd enters the catalogue.** Requested as a "replacement for DroppedNeedle", the premise deserved correcting: DroppedNeedle is not a bad choice, it is blocked by its download client, and **every** path to automated music acquisition goes through slskd or SABnzbd. Adding the client unblocks it without replacing it, and serves the whole stack: Sonarr, Radarr and Lidarr gain Usenet next to torrents. Usenet gets its **own directory tree** under `/data/usenet` — a torrent must keep seeding after the import, an NZB must not, and mixing them makes one delete what the other is still sharing. Four chained traps, each of them silent: its host whitelist rejects `http://sabnzbd:8080`; its API key was not generated; its pre-seeding did not run; and its factory categories have an **empty** directory, so "create if absent" left them unusable. Prowlarr, for its part, refuses to register without its own category. |
| **0.3.0** | **Seerr enters the catalogue.** The common successor to Jellyseerr and Overseerr. Its administrator account **is** the Jellyfin account — PlugArr generates none for it, that would be lying. It declares Sonarr and Radarr, anime folder included, then closes its setup **last**: the other way round would leave an instance that thinks it is ready and can request nothing. Its embedded OpenAPI specification **lies by omission**: `hostname` is the host alone and `port`, `useSsl`, `urlBase` are not declared even though the implementation reads them; `serverType` is mandatory although it is given as optional; and `minimumAvailability` only exists for Radarr. Three real attempts to find them, each behind a misleading message. |
| **0.3.0** | **The *arr credentials were not applied without a restart.** `PUT config/host` answers **202**, acknowledges, and changes nothing before the application comes back up — the same trap as for the API key. Ruled out along the way: this is not a special-character question, a purely alphanumeric password was refused the same way. The step now restarts the container and checks again. |
| **0.3.0** | **Audiobookshelf enters the catalogue.** It fills `books` and `audiobooks`, the two libraries PlugArr had been laying out since 0.1.12 with nobody reading them. Three traps recorded against a real instance: it takes **forty seconds** to start and answers 404 before that, which looks like a broken image; its SQLite database is read **with its `-wal` journal** or not at all, otherwise the `users` table looks empty while `/status` announces `isInit: true`; and `POST /init` answers 200 **with an empty body**, no token — where Silo's setup returns two. That last one gave 0 links out of 1 on the first real attempt. |
| **0.2.1** | **Restoring is done from the wizard.** It had first been left on the command line, on the grounds that a button would be dangerous — a weak argument, the command line has the same power. The real reason points at the right place: the admin console starts by reading a `stack.yml`, and on a freshly formatted machine there is none, since that is what the archive contains. A button there would have been unusable in the only case where it helps. The wizard, on the other hand, starts with nothing. An **Inspect the archive** button shows what it contains before overwriting anything, and replaces the confirmation. |
| **0.2.1** | **Full backup and restore.** Verified on a real stack rather than simulated: a marker placed in Sonarr, backup, **total destruction** — containers, volumes, folders — then a restore elsewhere. The marker came back, Silo returned *healthy* on the first try, and the re-wiring counted **12 links out of 12, zero created**: everything already existed. A button on the console; the restore stays on the command line, because it overwrites a configuration in place. |
| **0.2.0** | **arrsenal becomes PlugArr.** The name said "a pile of tools", which is what any *arr compose repository offers; what sets this project apart is that it **plugs them together**. 125 files. The hard part was none of the visible names: `discovery.py` recognises installed stacks by a **label**, never by their name, and renaming that label would have made every existing installation invisible — and therefore a candidate to be recreated over. Both markers are read, `plugarr.managed` and `arrsenal.managed`; only the first is written. The mechanical rename had also broken twenty-five French elisions: "qu'arrsenal sait faire" became "qu'PlugArr sait faire". |
| **0.2.0** | **The executable had no icon at all** — Windows gave it the generic one every console binary gets. Seven sizes from 16 to 256 px, generated by `scripts/icone.py` rather than committed as an opaque binary: transparent background, because a dark tile burned in becomes a black blob on a light taskbar; alpha channel derived from **chroma** rather than luminosity, which was eating the bottom of the purple descender. The wizard carries the brand colours. |
| **0.1.12** | **A library added to the catalogue did not reach existing installations.** `install` creates the directory tree, `wire` did not — and Sonarr flatly refuses a missing root folder: "Path '/data/media/anime' does not exist". Found while repairing a real stack right after anime was added. `wire` now guarantees the folders before wiring; the operation is idempotent and silent on an up-to-date installation. |
| **0.1.12** | **`plugarr wire` did not wait for the services to be ready, and answered with a Python traceback.** A fresh Sonarr spends a minute or more in its migrations: its port is published but nothing is listening behind it, and the wiring hit "Server disconnected without sending a response" — a message that sends you hunting for a network failure where there is only waiting. When the wait expired, the command ended on "Failed to execute script 'launcher'". `install` already handled both cases; `wire`, which is precisely the command you run to repair incomplete wiring, did not. |
| **0.1.12** | **Flood could not reach its download client under VPN.** Same cause as Prowlarr: Flood is not inside the tunnel, the client is and loses its DNS alias. Its password also left `docker-compose.yml`, where it sat in cleartext — the last secret to remain there after the WireGuard key. |
| **0.1.12** | **A tunnel that exits at your own address is now detected.** The first two checks declared it fine — the container *is* in the tunnel. Found on the test bench: a local WireGuard server translating addresses out through the home connection passed green. The tunnel's address is therefore compared against the machine's. Neither is ever logged. |
| **0.1.12** | **PlugArr now verifies that torrent traffic leaves through the tunnel.** It wrote `network_mode: service:gluetun` and considered the matter closed; yet that setting can be lost, and nothing would have said so. Two checks in `doctor` and behind the diagnostic button: the container's structure, then the real exit, asked of Gluetun's control server **from inside the client**. That test cannot pass by accident — only a container sharing Gluetun's network stack sees that `127.0.0.1`, verified both ways. No outside service is contacted, and the IP address is never logged. |
| **0.1.12** | **Prowlarr could not reach the download clients when the VPN was active.** A torrent client under VPN switches to `network_mode: service:gluetun` and loses its name on the network: `gluetun` is what must be targeted. `step_download_client` knew that, `step_prowlarr_download_client` hardcoded the service name. Sonarr, Radarr and Lidarr were wiring perfectly onto the same clients at the same moment, which made the failure unreadable. **Third divergence** between those two steps after the password and the key: they now read the same function. |
| **0.1.11** | **The admin console had had no JavaScript at all since 0.1.8.** The "add a service" confirmation message contained a string left open across two lines and three unescaped French apostrophes — invalid JavaScript, which took the whole script down with it. Start, stop, restart, rotate a key, apply an update: nothing responded. The HTML was perfectly well formed, though, and every Python test passed. Found by opening the page in a real browser; a test now checks that every `<script>` block has its quotes paired. |
| **0.1.11** | **Diagnostic and update check from the console.** Two buttons, requested from use. The update check already ran every fifteen minutes, but silently: there was no way to trigger it or to know when it had happened. The diagnostic existed only on the command line. |
| **0.1.11** | **A second installation overwrote the first.** Docker identifies a stack by its name, never by its directory, and that name was frozen to `plugarr`: installing a test stack next to a live one recreated the live one's six containers pointing elsewhere. The preflight was even reassuring — "port used by your own PlugArr stack" — which was true of the name and false of the installation. `--project-name` now exists, the wizard asks for it, and the preflight warns. |
| **0.1.11** | **Silo's database volume survived a reinstall.** PostgreSQL only applies `POSTGRES_PASSWORD` when it creates its database; on an already populated volume it ignores it silently. Reinstalling generated a new password, the volume kept the old one, and Silo restarted in a loop on "password authentication failed". The check only looked at disk. |
| **0.1.11** | **PlugArr promised a `.gitignore` it did not write.** The report and the access page announced that the credentials were "already in .gitignore"; no file was ever written. It is now. |
| **0.1.11** | **The WireGuard private key was written in cleartext in `docker-compose.yml`**, the only secret escaping the protected `.env`. It now goes through the `.env` like the others. |
| **0.1.11** | **The closing advice mentioned Prowlarr even when absent.** "Add your indexers in Prowlarr, they will flow down to Sonarr and Radarr" was displayed after a Silo-only installation, where none of the three applications existed. It now depends on what is installed. |
| **0.1.11** | Silo's database went through a mount onto the Windows disk: its first-start migrations took **49 minutes** instead of 5 seconds, and the installation gave up after 300 s while PostgreSQL was working perfectly. A Docker volume fixes both. Along the way, `config/silo-redis` stayed empty next to the `config/silo/redis` that Docker was creating itself. |
| **0.1.10** | **0.1.8 and 0.1.9 were uninstallable**: the VPN countries file made it neither into the executable nor into the package, and the wizard died on the VPN screen. A test now compares the real non-Python files against both packaging declarations, and the exe check walks through the wizard instead of just opening it. |
| **0.1.9** | The console starts on its own, on the host, and protects itself with a password. A cookie containing an accented character killed the request without authentication. |
| **0.1.8** | API key rotation, adding a service from the admin page, and a clickable VPN geographic filter. The same defect found three times: a service keeping the old secret with nothing saying so — autobrr, then Prowlarr's Application entry. |
| **0.1.7** | Recyclarr silently applied no profile at all as soon as a service ended up with two configuration files. Password rotation from the admin page. autobrr kept a download client's old password. |
| **0.1.6** | Three wizard crashes: a second indexer selected (`DuplicateIds`), an indexer error message containing an opening bracket, and fields becoming unreachable in a short window. An indexer's key no longer leaks to the screen or the log. |
| **0.1.5** | The VPN and the machine's address enter the wizard. Jellyfin kept an empty index: nothing triggered a scan after the libraries were created. A step that crashes no longer takes the whole wiring down with it. |
| **0.1.4** | Username of your choice, admin page reachable. |
| **0.1.3** | Explicit choice on an existing configuration, access page opened automatically. |

The full detail is in the [release notes](https://github.com/yannickuhrig1/plugarr/releases).
