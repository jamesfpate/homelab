## Server Setup
Setup for unraid homelab

### Unraid file/folder setup
- Create folders in appdata for each service. add any appdata files from repo to the appdata folder.
- add /mnt/user/appdata/env/.env folder via ssh and set env variables

### Unraid app setup
- run `scripts/create-networks.sh` once on the host to create the VLAN networks.
- install community app compose manager and add `compose/infra.yaml` as a stack named `komodo`, using `/mnt/user/appdata/env/.env`, and start it.
- in Komodo, create a Resource Sync named `homelab` pointing at this repo with resource path `komodo/resources.toml`, then run it to create the stacks in `stacks/`.
- in Komodo, add a Pushover alerter for failed deploys / updates.

### Updates
- pushing compose changes to `main` deploys them within ~5 minutes (Komodo "Deploy on push" procedure).
- container images auto-update daily at 03:00 (Komodo "Global Auto Update"). Pin a version in the image tag to hold it back.
- Komodo itself (`compose/infra.yaml`) is updated by hand in Compose Manager.

## Services
192.168.1.2 - Traefik - traefik.domain.com  
192.168.60.3 - Cloudflare Tunnel (public: request.domain.com -> Overseerr)  
192.168.1.4 - Dyndns - dyndns.domain.com  
192.168.1.6 - unraid proxy - urnaid.domain.com  
192.168.1.10 - Plex - plex.domain.com  
192.168.1.11 - pgadmin - db.domain.com  
192.168.1.13 - postgres  
unraid-ip:9120 - Komodo - komodo.domain.com  
192.168.40.40 - Home Assistant - ha.domain.com  
192.168.60.60 - qBittorrent - downloads.domain.com  
192.168.60.61 - Prowlarr - prowlarr.domain.com  
192.168.60.62 - Sonarr - tv.domain.com  
192.168.60.63 - Radarr - movies.domain.com  
192.168.60.64 - Bazarr - subtitles.domain.com  
192.168.60.65 - Overseerr - request.domain.com  
192.168.60.66 - sabnzbd - usenet.domain.com  
