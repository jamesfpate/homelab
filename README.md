# Homelab
Infrastructure-as-code for Docker services on Unraid: Docker Compose stacks deployed by Komodo, routed by Traefik.

## Layout
- `compose/infra.yaml` - Komodo v2 (core + periphery, FerretDB/Postgres backend). The only stack run by Unraid's Compose Manager.
- `stacks/` - service stacks, declared in `komodo/resources.toml` and deployed by Komodo's Resource Sync:
  - `proxy.yaml` - Traefik reverse proxy
  - `core.yaml` - core infrastructure (Postgres, pgAdmin, dyndns, Cloudflare Tunnel)
  - `home.yaml` - Home Assistant
  - `media.yaml` - Plex, *arr stack (incl. Lidarr), Seerr, sabnzbd, Pinchflat; gluetun + slskd (dormant, see Music)
  - `music.yaml` - Music Assistant on the IoT VLAN (Spotify -> Onkyo, KEF LSX II, Satellite1 speakers); Navidrome; musicflow (dormant, see Music)
  - `ai.yaml` - local AI backends on the RTX GPU (Ollama, Whisper, Chatterbox, Kokoro)
  - `chat.yaml` - Open WebUI (uses Ollama + Chatterbox/Kokoro)
  - `ash.yaml` - personal SvelteKit site (private ghcr.io image, internal only)
  - `typing.yaml` - kids typing game (`apps/typing`, static page, internal only)
- `apps/` - small first-party services built by Komodo from this repo (`musicflow`, `typing`). "Deploy on push" only
  redeploys a stack whose compose file changed, so an app-only change also needs a bump of the stack's `x-app-version`.
- `scripts/` - `create-networks.sh` (one-time VLAN setup), `update-komodo.sh` (daily Komodo update)
- `appdata/` - config files to copy into `/mnt/user/appdata/`
- `.local/` - private working notes (gitignored)

Validate a stack: `docker compose -f stacks/<stack>.yaml config`

## Conventions
- Networks: macvlan per VLAN, created once by `scripts/create-networks.sh` and `external` in every stack:
  - 192.168.1.x - Private/management (br0)
  - 192.168.20.x - Public services (br0.20)
  - 192.168.40.x - IoT (br0.40)
  - 192.168.60.x - Downloads/media (br0.60)
  - 192.168.70.x - Cameras (br0.70; UniFi Protect only, no Docker network)
- Container IPs are static (see Services below).
- HTTP services are routed via Traefik labels as `<service>.<domain>`; Traefik handles TLS (wildcard cert, Cloudflare DNS-01; needs `CF_API_EMAIL` and `CF_DNS_API_TOKEN`) and the LAN IP allowlist.
- Secrets/env live only in `/mnt/user/appdata/env/.env` on the server, never in the repo. Compose files assume Unraid paths; app data lives in `/mnt/user/appdata/<service>/`.
- Pin versions via image tags; databases stay on a fixed major.
- Unraid's `/etc` is RAM-backed, so Komodo's keys, backups and periphery root live under `/mnt/user/appdata/komodo/`.
- GPUs: Intel iGPU for Plex transcoding; NVIDIA RTX PRO 4000 Blackwell (24 GB, Unraid Nvidia Driver plugin, open kernel module) for the ai stack via `runtime: nvidia`.
- Camera person detection is done by UniFi Protect on the UDM SE and surfaced in Home Assistant via the UniFi Protect integration.

## Server Setup

### Unraid file/folder setup
- Create folders in appdata for each service. add any appdata files from repo to the appdata folder.
- add /mnt/user/appdata/env/.env folder via ssh and set env variables

### Unraid app setup
- run `scripts/create-networks.sh` once on the host to create the VLAN networks.
- `mkdir -p /mnt/user/appdata/komodo/ferretdb-state && chown 1000:1000 /mnt/user/appdata/komodo/ferretdb-state` (FerretDB runs as uid 1000).
- install community app compose manager and add `compose/infra.yaml` as a stack named `komodo`, using `/mnt/user/appdata/env/.env`, and start it.
- in Komodo, create a Resource Sync named `homelab` pointing at this repo with resource path `komodo/resources.toml`, then run it to create the stacks in `stacks/`.
- in Komodo, add a Pushover alerter for failed deploys / updates.

### Updates
- pushing compose changes to `main` deploys them within ~5 minutes (Komodo "Deploy on push" procedure).
- container images auto-update daily at 03:00 (Komodo "Global Auto Update"). Pin a version in the image tag to hold it back.
- Komodo itself (`compose/infra.yaml`) is updated daily at 04:00 by `scripts/update-komodo.sh`, run from the Unraid User Scripts plugin (installs infra.yaml from main after validating it, then pulls new images).

## UniFi network notes
- VLANs 20/40/60/70 have "Isolate Network" on (auto "Isolated Networks" block policies, priority 30000).
- Custom firewall policy "Main to IoT": allow 192.168.1.0/24 -> 192.168.40.0/24, auto-allow return traffic
  (lets phones/computers control and cast to IoT devices; IoT still can't initiate into main).
- Gateway mDNS Proxy: Custom, main + IoT, all services (Spotify Connect / Cast / AirPlay discovery across VLANs).
- IGMP snooping off on main and IoT (multicast discovery reliability).
- Internal names are per-host UDM local DNS records (A -> 192.168.1.2, Traefik); no wildcard. New Traefik service = add a record.
- Keep 192.168.1.50-53 and other container IPs outside the UDM DHCP range (Docker assigns them, UDM doesn't know).
- If casting to the Onkyo wakes the TV: LG SIMPLINK Auto Power Sync off (keeps ARC/volume control).

## Hosts & devices
192.168.1.1 - UniFi Dream Machine SE (gateway, UniFi Protect cameras, WireGuard VPN server for remote access)  
192.168.1.41 - KVM (remote console for the Unraid server)  
192.168.1.42 - Unraid server (iris) - unraid.domain.com  

## Services
192.168.1.2 - Traefik - traefik.domain.com  
192.168.1.4 - Dyndns - dyndns.domain.com  
192.168.1.6 - unraid proxy (routes unraid.domain.com to 192.168.1.42)  
192.168.1.10 / 192.168.60.10 - Plex - plex.domain.com  
192.168.1.11 - pgadmin - db.domain.com  
192.168.1.13 - postgres  
192.168.1.14 / 192.168.40.46 / 192.168.60.14 - Navidrome - listen.domain.com  
192.168.1.25 - ash (personal site, internal only) - ash.domain.com  
192.168.1.26 - typing (kids typing game, internal only) - type.domain.com  
192.168.1.27 - musicflow dashboard (inbox by source, keep rates) - inbox.domain.com  
192.168.1.40 / 192.168.40.40 - Home Assistant - ha.domain.com  
192.168.40.45 - Music Assistant (IoT VLAN, with its speakers) - music.domain.com  
192.168.1.50 - Whisper speech-to-text (Wyoming :10300, GPU)  
192.168.1.51 - Chatterbox Turbo text-to-speech (Wyoming :10300, GPU)  
192.168.1.52 - Ollama local LLM (:11434, GPU)  
192.168.1.53 - Kokoro text-to-speech (Wyoming :10300, CPU)  
192.168.1.54 - chat.domain.com  
192.168.1.42:9120 - Komodo - komodo.domain.com  
192.168.60.3 - Cloudflare Tunnel (public: request.domain.com -> Seerr)  
192.168.60.61 - Prowlarr - indexer.domain.com  
192.168.60.62 - Sonarr - tv.domain.com  
192.168.60.63 - Radarr - movies.domain.com  
192.168.60.64 - Bazarr - subtitles.domain.com  
192.168.60.65 - Seerr (was Overseerr) - request.domain.com  
192.168.60.66 - sabnzbd - usenet.domain.com  
192.168.60.67 - Pinchflat (YouTube -> kids-youtube) - youtube.domain.com  
192.168.60.68 - Lidarr - albums.domain.com  
192.168.60.69 - gluetun + slskd (phase 2) - soulseek.domain.com  
192.168.60.71 - musicflow (phase 2, no UI)  

## Music
Self-hosted replacement for Spotify discovery, with offline listening on Android. Status: **phase 1** (library + playback).
Phase 2 services are in the compose files with `profiles: ["discovery"]`, so Komodo doesn't start them.

### How it works
- Files: `/mnt/user/plexmedia/music/` -> `library/` (permanent), `inbox/<source>/` (auditioning), `playlists/` (`.nsp` smart playlists).
- Navidrome serves everything. Users: `james` (Symfonium on Android, Feishin on Mac; linked to ListenBrainz) and
  `house` (Music Assistant; no ListenBrainz). Stars, ratings and plays are per user, so household listening never
  reaches recommendations or the inbox. Spotify stays shared and is never connected to ListenBrainz.
- Lidarr (nightly + Tubifarry plugin) fills `library/` with albums via Prowlarr + sabnzbd (Usenet).
- Phase 2 inbox: always `INBOX_SIZE` (50) unheard songs, about 3 hours: a day of commuting plus extra.
  - Daily 19:30 `musicflow ingest` counts unheard inbox tracks and adds only enough to get back to 50, taking
    one at a time from ListenBrainz Weekly Exploration, ListenBrainz Fresh Releases, Last.fm similar artists (seeded
    from a random 8 of your starred artists each night) and each subreddit in `SUBREDDITS`
    (all-time top 100, then month, then week: `REDDIT_WINDOWS`)
    (`inbox/<source>/`). It never goes past 50 and never re-offers anything it has tried before.
  - Symfonium keeps the `Inbox` and `Starred` smart playlists downloaded.
  - Daily 19:00 `musicflow promote`: starred -> ListenBrainz love, beets-tagged into `library/`, re-starred;
    rated 1 -> ListenBrainz hate, deleted; heard (a logged play) and not starred -> deleted at the next promote
    (`PLAYED_GRACE_HOURS=0`; a logged play needs about half the track, so quick skips stay unheard). Only an
    explicit 1-star rating is reported to ListenBrainz as a dislike (`HEARD_FEEDBACK=none`).
    Unheard songs are never deleted. It only ever deletes under `inbox/`.
  - Skipping early doesn't log a play, so a skipped track stays in the inbox; rate it 1 to clear it.
- slskd runs behind gluetun on its own AirVPN WireGuard device with a forwarded port (Soulseek needs inbound).
  The UDM `downloads-to-airvpn` policy route stays paused: it can't pass an inbound port and would also
  send Seerr's Cloudflare Tunnel through Switzerland.
- Why these tools (Sept 2026): Navidrome + Symfonium is the only pairing with auto-updating offline playlists and
  separate star/rating fields; Jellyfin has no track ratings, Plexamp downloads don't drop deleted tracks.
  Explo (and SoulSync, DroppedNeedle) were considered, but none do the star-to-keep loop or respect a fixed inbox
  size (Explo drops its whole weekly batch regardless), hence `apps/musicflow`, which also pulls Weekly Exploration.

### Phase 1 setup
1. `mkdir -p /mnt/user/plexmedia/music/{library,inbox,playlists} /mnt/user/downloads/slskd /mnt/user/appdata/{navidrome,lidarr}`,
   `chown -R 1003:100` them; copy `appdata/music/playlists/Starred.nsp` into `/mnt/user/plexmedia/music/playlists/`.
2. Add `NAVIDROME_USER` / `NAVIDROME_PASSWORD` to the server `.env`. Push; Komodo deploys Navidrome and Lidarr.
3. UDM local DNS: `listen` and `albums` -> 192.168.1.2.
4. Navidrome (listen.<domain>): create `james` first (admin; owns the smart playlists), then `house`.
   Accounts: MusicBrainz + ListenBrainz; in Navidrome as `james`, Personal > ListenBrainz > link.
5. Lidarr (albums.<domain>): root folder `/music/library`; download client sabnzbd (category `music`,
   `/downloads/usenet`); add Lidarr as an app in Prowlarr. System > Plugins: install Tubifarry, then set its
   metadata source to the community mirror (Lidarr's own metadata server is unreliable in 2026).
6. Seed: add artists in Lidarr. For a track list, skim an Exportify CSV of Spotify likes first (shared account).
7. Apps: Symfonium -> `https://listen.<domain>` as `james`, offline rule for playlist `Starred` (Wi-Fi only);
   Feishin on the Mac; Music Assistant -> Subsonic provider `http://192.168.40.46:4533` as `house`.
   Away from home: UDM WireGuard. Stars only in Symfonium/Feishin/Navidrome web (Music Assistant is the `house` user).

### Phase 2: turn on discovery (after a few weeks of listening as `james`)
1. AirVPN Client Area: Config Generator -> new device `slskd`, WireGuard; Ports -> add a port, assign to `slskd`.
   Soulseek account: register by logging in once with any client. Fill the phase 2 vars in the server `.env`.
2. `mkdir -p /mnt/user/appdata/{gluetun,slskd,musicflow}`, `chown` as above.
3. Copy `appdata/music/playlists/Inbox.nsp` into the music `playlists/` folder; Symfonium offline rule for `Inbox`.
4. Delete the `profiles: ["discovery"]` lines in `stacks/media.yaml` and `stacks/music.yaml`; push.
   DNS: `soulseek` -> 192.168.1.2.
5. Lidarr: Tubifarry Soulseek download client -> `http://192.168.60.69:5030` + `SLSKD_API_KEY`, path `/downloads/slskd`.
6. `musicflow` starts with `DRY_RUN=true`: check `docker logs musicflow` after the first 19:00 run, or run
   `docker exec musicflow python -m musicflow promote` by hand; then set `DRY_RUN=false` in `stacks/music.yaml`.
   Other commands: `ingest all|exploration|fresh|r/<subreddit>`, `sync-loves`, `seed /config/liked.csv --limit 500`.
   Local LLM (Ollama, `OLLAMA_URL`): parses Reddit titles and scores every candidate 0–10 for taste. `LLM_FILTER=false`
   is shadow mode (scores logged + on the dashboard, nothing skipped); flip to true once the score predicts keeps.
   Album stars: star an album in Navidrome/Symfonium/Feishin and `musicflow wants` (every 30 min) adds it to Lidarr
   and starts a search; the dashboard lists them under "Wanted albums".
   Provenance: each inbox file gets a comment tag `musicflow: <source> <date>`, Navidrome gets an `Inbox - <source>`
   smart playlist per source, and every add/keep/dislike/drop is logged to `/config/musicflow.db`, which feeds the
   dashboard at inbox.<domain> (`musicflow-web`; copy `appdata/musicflow/nginx.conf` to `/mnt/user/appdata/musicflow/`).
7. Pin/upgrade deliberately: Lidarr nightly, slskd, gluetun and Navidrome are pinned so the 03:00
   auto-update can't change them. yt-dlp inside musicflow self-updates daily (YouTube breaks it often).
8. `musicflow` is built from `apps/musicflow` (`pull_policy: build`). A plain redeploy reuses the old image, so after
   changing its code rebuild it (Komodo stack build/redeploy with build, or `docker compose build musicflow`).

