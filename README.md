## Server Setup
Setup for unraid homelab

### Unraid file/folder setup
- Create folders in appdata for each service. add any appdata files from repo to the appdata folder.
- add /mnt/user/appdata/env/.env folder via ssh and set env variables

### Unraid app setup
- install community app compose manager and add portainer-traefik.yaml as a stack and start it.
- connect portainer to github and add docker compose stacks
