# iris
Personal server config
├── kubernetes/
│   ├── clusters/
│   │   └── home-cluster/
│   │       ├── cluster-config.yaml
│   │       └── argocd-apps.yaml
│   │
│   ├── namespaces/
│   │   ├── monitoring.yaml
│   │   └── home-services.yaml
│   │
│   └── applications/
│       ├── traefik/
│       ├── home-assistant/
│       └── arr/
│
├── docker/
│   ├── plex/
│   │   ├── docker-compose.yaml
│   │   └── README.md
│   └── media-management/
│       ├── docker-compose.yaml
│       └── README.md
│
├── scripts/
│   ├── media-backup.sh
│   └── kubernetes-setup.sh
