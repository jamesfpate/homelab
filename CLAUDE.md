# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a homelab infrastructure-as-code repository for managing Docker-based services on Unraid. It uses Docker Compose with Komodo for orchestration and Traefik for reverse proxy/SSL management.

## Common Commands

### Service Deployment
```bash
# Deploy/update a service stack via Komodo (UI, or push to main + Resource Sync)
# Stack files are in /stacks/ directory, declared in komodo/resources.toml:
# - proxy.yaml - Traefik reverse proxy
# - core.yaml - Core infrastructure (databases, DNS, monitoring)
# - home.yaml - Home automation (Home Assistant, Frigate)
# - media.yaml - Media services (Plex, *arr stack)
# - public.yaml - Public services (n8n)

# View service logs (on Unraid host)
docker logs [container_name]

# Check service status
docker ps -a | grep [service_name]
```

### Working with Docker Compose Files
```bash
# Validate compose syntax
docker compose -f stacks/[stack].yaml config

# Check what would be deployed (dry run)
docker compose -f stacks/[stack].yaml config --services
```

## Architecture Overview

### Network Architecture
The homelab uses VLAN segmentation with macvlan networks:
- **192.168.1.x** - Private/management VLAN (br0)
- **192.168.20.x** - Public services VLAN (br0.20)
- **192.168.40.x** - IoT devices VLAN (br0.40)
- **192.168.60.x** - Downloads/media VLAN (br0.60)
- **192.168.70.x** - Security cameras VLAN (br0.70)

### Service Architecture
1. **Infrastructure Layer** (`compose/infra.yaml`, deployed by Unraid Compose Manager)
   - Komodo v2 (core + periphery + MongoDB): deploys the service stacks from this repo
   - VLAN macvlan networks are created once by `scripts/create-networks.sh` and are external in every stack

2. **Service Stacks** (deployed via Komodo from `/stacks/`, declared in `komodo/resources.toml`)
   - Each stack is isolated with its own compose file
   - Services communicate through Traefik labels for routing
   - All services use environment variables from `/mnt/user/appdata/env/.env`

### Key Patterns
- **Service Discovery**: All HTTP services exposed via `service.local.example.com` subdomains
- **SSL/Security**: Traefik handles all SSL certificates and IP whitelisting
- **Data Persistence**: Application data in `/mnt/user/appdata/[service]/`
- **Hardware Access**: Intel GPU passed through for Plex/Frigate transcoding
- **Updates**: Komodo auto-deploys compose changes pushed to main (~5 min) and auto-updates images daily at 03:00; pin versions via image tags (databases stay on a fixed major)

### Important Considerations
- Environment variables are NOT stored in the repo (kept in server's `.env` file)
- All compose files assume Unraid paths (`/mnt/user/...`)
- Services are deployed through a Komodo Resource Sync of this repo; Komodo config lives in `/mnt/user/appdata/komodo/compose.env`
- Unraid's `/etc` is RAM-backed, so Komodo's keys/backups/periphery root are kept under `/mnt/user/appdata/komodo/`
- IP addresses are statically assigned per the README.md mappings
- **SSL Renewal**: Traefik requires `CF_API_EMAIL=${EMAIL}` and `CF_DNS_API_TOKEN=${CF_DNS_API_TOKEN}` environment variables for Let's Encrypt SSL certificate renewal via Cloudflare DNS challenge

## Deployment Notes
- Traefik runs as the `proxy` stack in Komodo; only Komodo itself uses Unraid's Docker Compose extension
- Service stacks are managed in Komodo
- The primary infrastructure compose file is located at `@compose/infra.yaml`