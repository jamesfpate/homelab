#!/bin/bash
# One-time setup on the Unraid host: create the VLAN macvlan networks shared by every stack.
# br0 (192.168.1.x) is Unraid's own custom network and already exists.
# Safe to re-run; existing networks are skipped.
set -euo pipefail

create() {
  local name=$1 parent=$2 subnet=$3 gateway=$4
  if docker network inspect "$name" >/dev/null 2>&1; then
    echo "exists: $name"
  else
    docker network create -d macvlan -o parent="$parent" \
      --subnet="$subnet" --gateway="$gateway" "$name"
  fi
}

create vlan-public    br0.20 192.168.20.0/24 192.168.20.1
create vlan-iot       br0.40 192.168.40.0/24 192.168.40.1
create vlan-downloads br0.60 192.168.60.0/24 192.168.60.1
create vlan-cameras   br0.70 192.168.70.0/24 192.168.70.1
