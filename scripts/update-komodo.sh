#!/bin/bash
# Keeps the Komodo bootstrap stack (compose/infra.yaml) up to date without Komodo updating itself:
#   1. downloads compose/infra.yaml from main and validates it
#   2. installs it as the Compose Manager stack's compose file
#   3. pulls newer images (komodo-core/periphery :2 track the latest 2.x) and recreates what changed
# Run on the Unraid host via the User Scripts plugin, e.g. daily at 04:00 (after Komodo's 03:00
# Global Auto Update). Safe to run by hand.
set -euo pipefail

REPO_FILE=https://raw.githubusercontent.com/jamesfpate/homelab/main/compose/infra.yaml
ENV_FILE=/mnt/user/appdata/env/.env

# Find the Compose Manager project from the running container instead of hardcoding paths.
label() { docker inspect komodo-core --format "{{index .Config.Labels \"com.docker.compose.$1\"}}"; }
PROJECT=$(label project)
COMPOSE_FILE=$(label project.config_files | cut -d, -f1)
[ -n "$PROJECT" ] && [ -f "$COMPOSE_FILE" ] || { echo "Can't locate the Komodo compose project"; exit 1; }

compose() { docker compose -p "$PROJECT" --env-file "$ENV_FILE" -f "$1" "${@:2}"; }

tmp=$(mktemp --suffix=.yaml)
trap 'rm -f "$tmp"' EXIT
curl -fsSL "$REPO_FILE" -o "$tmp"
compose "$tmp" config -q # refuse to apply an invalid file

if ! cmp -s "$tmp" "$COMPOSE_FILE"; then
  echo "infra.yaml changed on main; installing it to $COMPOSE_FILE"
  cp "$COMPOSE_FILE" "$COMPOSE_FILE.prev"
  cp "$tmp" "$COMPOSE_FILE"
fi

compose "$COMPOSE_FILE" pull --quiet
compose "$COMPOSE_FILE" up -d --remove-orphans
docker image prune -f >/dev/null
echo "Komodo stack up to date"
