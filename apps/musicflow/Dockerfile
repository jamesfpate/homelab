# musicflow: weekly star-to-keep promote/cleanup + extra recommendation sources for Navidrome.
# Built by Komodo from this repo (stacks/music.yaml, pull_policy: build).
FROM python:3.12-slim

ARG SUPERCRONIC_VERSION=v0.2.49
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libchromaprint-tools curl ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL -o /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
 && chmod +x /usr/local/bin/supercronic

# yt-dlp needs a JS runtime for YouTube; the yt-dlp binary itself lives in /config/bin and self-updates daily.
COPY --from=denoland/deno:bin-2.9.7 /deno /usr/local/bin/deno

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY musicflow /app/musicflow
COPY beets.yaml crontab entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

ENV PYTHONPATH=/app PYTHONUNBUFFERED=1 BEETSDIR=/config/beets HOME=/config PATH="/config/bin:${PATH}"
WORKDIR /app
ENTRYPOINT ["/app/entrypoint.sh"]
