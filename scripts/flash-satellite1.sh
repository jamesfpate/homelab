#!/bin/bash
# Builds appdata/esphome/satellite1-4f31a0.yaml and flashes it to the Satellite1 over Wi-Fi. Run on the Unraid host.
# Copy the repo's appdata/esphome/ to /mnt/user/appdata/esphome/ first. The build cache stays in that folder, so
# rebuilds after the first one are quick. Pass "compile" to build without flashing.
set -euo pipefail
ESPHOME_VERSION=2026.7.3 # match FutureProofHomes' requirements.txt at the pinned ref; newer ESPHome rejects their config
DEVICE=192.168.1.109
CMD=${1:-run}
ARGS=(); [ "$CMD" = run ] && ARGS=(--device "$DEVICE" --no-logs)
# On br0 with a fixed IP (192.168.1.8, free; not Docker's pick, which could land on a LAN device) so the OTA upload can
# reach the satellite.
docker run --rm --network br0 --ip 192.168.1.8 -v /mnt/user/appdata/esphome:/config \
  ghcr.io/esphome/esphome:"$ESPHOME_VERSION" "$CMD" /config/satellite1-4f31a0.yaml "${ARGS[@]}"
