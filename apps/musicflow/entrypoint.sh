#!/bin/sh
set -eu
mkdir -p /config/beets /config/bin /config/logs
[ -f /config/beets/config.yaml ] || cp /app/beets.yaml /config/beets/config.yaml
if [ ! -x /config/bin/yt-dlp ]; then
  curl -fsSL -o /config/bin/yt-dlp https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_linux
  chmod +x /config/bin/yt-dlp
fi
# One-off commands: docker exec musicflow python -m musicflow <cmd>
exec supercronic -passthrough-logs /app/crontab
