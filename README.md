## Server Setup
Setup for unraid homelab

### Unraid file/folder setup
- Create folders in appdata for each service. add any appdata files from repo to the appdata folder.
- add /boot/custom/.env folder via ssh and set env variables

### Unraid app setup
- install community app compose manager and add portainer-init.yaml as a stack and start it.
- connect portainer to github and pull
- once you have verified the new portainer is working you can delete portainer-init. 

## Services
192.168.1.2 - Traefik - traefik.domain.com
192.168.1.3 - Cloudflare Tunnel
192.168.1.4 - Dyndns - dyndns.domain.com
192.168.5.5 - Socket Proxy
192.168.1.10 - Plex - plex.domain.com
192.168.1.11 - Adminer - pg.domain.com
192.168.1.12 - Portainer - portainer.domain.com
192.168.40.40 - Home Assistant - ha.domain.com
192.168.70.70 - Frigate - frigate.domain.com
192.168.60.60 - qBittorrent - downloads.domain.com
192.168.60.61 - Prowlarr - prowlarr.domain.com
192.168.60.62 - Sonarr - tv.domain.com
192.168.60.63 - Radarr - movies.domain.com
192.168.60.64 - Bazarr - subtitles.domain.com
192.168.60.65 - Overseerr - request.domain.com

