# Homelab
Infrastructure-as-code for Docker services on Unraid: Docker Compose stacks deployed by Komodo, routed by Traefik.

## Layout
- `compose/infra.yaml` - Komodo v2 (core + periphery, FerretDB/Postgres backend). The only stack run by Unraid's Compose Manager.
- `stacks/` - service stacks, declared in `komodo/resources.toml` and deployed by Komodo's Resource Sync:
  - `proxy.yaml` - Traefik reverse proxy
  - `core.yaml` - core infrastructure (Postgres, pgAdmin, dyndns, Cloudflare Tunnel)
  - `home.yaml` - Home Assistant
  - `media.yaml` - Plex, *arr stack, Seerr, sabnzbd, Pinchflat
  - `music.yaml` - Music Assistant on the IoT VLAN (Spotify -> Onkyo, KEF LSX II, Satellite1 speakers)
  - `ai.yaml` - local AI backends on the RTX GPU (Ollama, Whisper, Chatterbox, Kokoro)
  - `chat.yaml` - Open WebUI (uses Ollama + Chatterbox/Kokoro)
  - `ash.yaml` - personal SvelteKit site (private ghcr.io image, internal only)
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
192.168.1.25 - ash (personal site, internal only) - ash.domain.com  
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
