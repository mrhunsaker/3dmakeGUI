# Containers

This project includes Docker and Podman deployment artifacts for running the
NiceGUI web application in a containerized environment.

## Files

| File                                                                                       | Purpose                             |
| ------------------------------------------------------------------------------------------ | ----------------------------------- |
| [Dockerfile](https://github.com/mrhunsaker/3dmakeGUI/blob/main/Dockerfile)                 | Multi-stage build for runtime image |
| [docker-compose.yml](https://github.com/mrhunsaker/3dmakeGUI/blob/main/docker-compose.yml) | Docker Compose deployment           |
| [podman-compose.yml](https://github.com/mrhunsaker/3dmakeGUI/blob/main/podman-compose.yml) | podman-compose deployment           |
| [container.yaml](https://github.com/mrhunsaker/3dmakeGUI/blob/main/container.yaml)         | `podman play kube` Pod spec         |

## Docker

```bash
docker compose build
docker compose up -d
```

Open: <http://localhost:8080>

Stop:

```bash
docker compose down
```

## Podman Compose

```bash
podman build -t 3dmake-gui-wrapper:2026.04.29 .
podman-compose up -d
```

Stop:

```bash
podman-compose down
```

## Podman Kube Play

```bash
podman build -t 3dmake-gui-wrapper:2026.04.29 .
podman play kube container.yaml
```

Stop:

```bash
podman play kube --down container.yaml
```

## Volumes

Default named volumes persist:

- project files
- GUI settings/configuration

Adjust volume mappings in compose/pod specs if you want direct bind mounts to
host directories.

## Security Defaults

Container files are configured with:

- non-root execution (UID/GID 1001)
- dropped capabilities (`cap_drop: [ALL]`)
- read-only root filesystem
- temporary writable mounts for `/tmp` and `/run`
- localhost-only published port by default
