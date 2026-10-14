#!/bin/bash
# Starts containers that are stuck in "created" (recreated by a deploy or auto-update but never started: Docker's
# restart policy only covers containers that ran and exited, so these sit there until someone notices; Traefik
# did exactly that on 2026-10-07 and took every LAN app down for 40 h) and restarts Traefik if its health check
# is failing. Run on the Unraid host via the User Scripts plugin every 5 minutes. Safe to run by hand.
set -uo pipefail

for c in $(docker ps -a --filter status=created --format '{{.Names}}'); do
  echo "$(date '+%F %T') starting stuck container: $c"
  docker start "$c" || echo "$(date '+%F %T') FAILED to start $c"
done

if [ "$(docker inspect -f '{{.State.Health.Status}}' traefik 2>/dev/null)" = "unhealthy" ]; then
  echo "$(date '+%F %T') traefik unhealthy, restarting"
  docker restart traefik
fi

# Traefik reaches komodo-core over the "komodo" network. If that network is recreated (Komodo's own compose
# restarting) while Traefik keeps running, Traefik silently drops off it and komodo.jamespate.net returns 504
# (seen 2026-10-13). Reattach it.
if docker network inspect komodo >/dev/null 2>&1 && \
   ! docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' traefik 2>/dev/null | grep -qw komodo; then
  echo "$(date '+%F %T') traefik not on komodo network, reattaching"
  docker network connect komodo traefik
fi
