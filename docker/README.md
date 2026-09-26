# Docker Development Guide

This guide provides instructions for building and running the LiteLLM application using Docker and Docker Compose.

> **Just want to run LiteLLM?** This guide builds from source. To run the published
> image instead, use `docker-compose.quickstart.yml` in this directory — the
> two-service stack (gateway + Postgres) that the
> [Docker quickstart](https://docs.litellm.ai/docs/proxy/docker_quick_start) documents:
>
> ```bash
> curl -sSLO https://github.com/BerriAI/litellm/raw/main/docker/docker-compose.quickstart.yml
> printf 'LITELLM_MASTER_KEY=sk-%s\nLITELLM_SALT_KEY=sk-%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" > .env
> docker compose -f docker-compose.quickstart.yml up -d
> ```

## Prerequisites

- Docker
- Docker Compose

## Building and Running the Application

To build and run the application, you will use the `docker-compose.yml` file located in the root of the project. It builds the `Dockerfile` in the repository root, the one image LiteLLM ships, which runs as a non-root user by default

## One image, many components

Every LiteLLM container runs the same image. The first word of the container command (or the `LITELLM_COMPONENT` environment variable when the command carries only flags) picks the process the container runs, and everything after it is handed to that process unchanged:

| Component    | Runs                                                | Port |
|--------------|-----------------------------------------------------|------|
| `proxy`      | `litellm ...` (everything in one process, default)  | 4000 |
| `gateway`    | `python -m gateway.launch ...` (inference routes)   | 4000 |
| `backend`    | `uvicorn backend.main:app ...` (management routes)  | 4001 |
| `ui`         | nginx serving the static admin UI                   | 3000 |
| `migrations` | `python migrations/run.py`, `prisma migrate deploy` then exit | |
| `metrics`    | `python -m litellm.proxy.prometheus_metrics_server ...` | `--port` |
| `collector`  | `python -m litellm.proxy.collector ...`             | |

```bash
docker run -p 4000:4000 litellm --config /app/config.yaml         # proxy, exactly as before
docker run -p 4000:4000 litellm gateway --port 4000               # componentized data plane
docker run -p 4001:4001 -e LITELLM_COMPONENT=backend litellm      # same, chosen through the env
docker run -p 3000:3000 --read-only --tmpfs /tmp litellm ui       # admin UI behind nginx
docker run -e DATABASE_URL=... litellm migrations                 # one-off schema migration job
docker run -it litellm sh                                         # anything else runs verbatim
```

PgBouncer is not a separate component: `LITELLM_PGBOUNCER_ENABLED=true` starts an in-container PgBouncer in front of `DATABASE_URL` inside `proxy` and `gateway`. `USE_DDTRACE=true` wraps whichever component runs with `ddtrace-run`, and `PROMETHEUS_MULTIPROC_DIR` is emptied of stale samples before any workers fork

The image runs as uid `65532` (`nonroot` in the Wolfi base) and also works as an arbitrary uid in gid 0, the shape OpenShift `restricted-v2` assigns, because everything it writes at runtime lives under `/app/.cache`, `/var/lib/litellm` and `/tmp`. Mount those (or set `readOnlyRootFilesystem` with emptyDirs there) for a read-only root filesystem. Prisma's CLI and engines are baked under `/opt/prisma`, so migrations need neither network nor a writable home

### 1. Set the Master Key

The application requires a `LITELLM_MASTER_KEY` for signing and validating tokens. You must set this key as an environment variable before running the application.

Create a `.env` file in the root of the project and add the following line:

```
LITELLM_MASTER_KEY=your-secret-key
```

Replace `your-secret-key` with a strong, randomly generated secret.

### 2. Build and Run the Containers

Once you have set the `LITELLM_MASTER_KEY`, you can build and run the containers using the following command:

```bash
docker compose up -d --build
```

This command will:

-   Build the Docker image from the root `Dockerfile`.
-   Start the `litellm`, `litellm_db`, and `prometheus` services in detached mode (`-d`).
-   The `--build` flag ensures that the image is rebuilt if there are any changes to the Dockerfile or the application code.

### 3. Verifying the Application is Running

You can check the status of the running containers with the following command:

```bash
docker compose ps
```

To view the logs of the `litellm` container, run:

```bash
docker compose logs -f litellm
```

### 4. Stopping the Application

To stop the running containers, use the following command:

```bash
docker compose down
```

## Hardened / Offline Testing

To ensure changes are safe for non-root, read-only root filesystems and restricted egress, always validate with the hardened compose file:

```bash
docker compose -f docker-compose.yml -f docker-compose.hardened.yml build --no-cache
docker compose -f docker-compose.yml -f docker-compose.hardened.yml up -d
```

This setup:
- Builds the root `Dockerfile` with Prisma engines and Node toolchain baked into the image.
- Runs the proxy as an arbitrary non-root uid with a read-only rootfs and only writable tmpfs mounts:
  - `/tmp`
  - `/app/.cache` (Prisma/NPM cache under `HOME`)
  - `/app/migrations-out` (Prisma migration workspace; backing `LITELLM_MIGRATION_DIR`)
- Pre-builds and serves the admin UI from `/var/lib/litellm/ui` (with the `.litellm_ui_ready` marker) and `/var/lib/litellm/assets`.
- Routes all outbound traffic through a local Squid proxy that denies egress, so Prisma migrations must use the cached CLI and engines.

You should also verify offline Prisma behaviour with:

```bash
docker run --rm --network none --entrypoint prisma ghcr.io/berriai/litellm:main-stable --version
```

This command should succeed (showing engine versions) even with `--network none`, confirming that Prisma binaries are available without network access.

## Troubleshooting

-   **`build_admin_ui.sh: not found`**: This error can occur if the Docker build context is not set correctly. Ensure that you are running the `docker-compose` command from the root of the project.
-   **`Master key is not initialized`**: This error means the `LITELLM_MASTER_KEY` environment variable is not set. Make sure you have created a `.env` file in the project root with the `LITELLM_MASTER_KEY` defined.
