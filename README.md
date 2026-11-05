# OpsDesk

[![CI](https://github.com/kennethikugbe/opsdesk/actions/workflows/ci.yml/badge.svg)](https://github.com/kennethikugbe/opsdesk/actions/workflows/ci.yml)
[![Security](https://github.com/kennethikugbe/opsdesk/actions/workflows/security.yml/badge.svg)](https://github.com/kennethikugbe/opsdesk/actions/workflows/security.yml)
[![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](./LICENSE)

OpsDesk is a support-ticket application built as a **DevOps and DevSecOps lab**. A team can raise a request with a title, requester, category, priority and description, filter and read requests, update their status, and see a live summary. The application itself is deliberately small — the point of the project is everything wrapped around it: containerisation with enforced isolation, a persistent data volume, two GitHub Actions pipelines, and secret, dependency and container scanning wired into every push.

It runs entirely on a local lab — a Windows host and an Ubuntu guest VM — with no cloud dependency. It is a learning environment, not a production service; see [Known limitations](#known-limitations-and-whats-next).

---

## What it does

| Area | Detail |
| --- | --- |
| **Backend** | Python 3.14 / Flask JSON API served by Gunicorn |
| **Frontend** | Separate static HTML/CSS/JS, no build step, calls the API with relative URLs |
| **Database** | SQLite, held in a permissioned Docker named volume |
| **Tests** | 20 pytest cases covering the API and the frontend/backend separation |
| **Containers** | Two independently deployable images behind Nginx |
| **Pipelines** | CI and Security, both green on every push to `main` |

### API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api` | Service identity and version info |
| `GET` | `/health/live` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe, verifies the database is reachable |
| `GET` | `/api/summary` | Counts: `open`, `in_progress`, `resolved`, `total` |
| `GET` | `/api/tickets` | List and filter requests, newest first |
| `POST` | `/api/tickets` | Create a request |
| `GET` | `/api/tickets/<id>` | Read one request |
| `PATCH` | `/api/tickets/<id>` | Update status |

Every response carries hardened headers — `Content-Security-Policy: default-src 'self'`, `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY` — and the test suite asserts them, so removing one fails the build.

---

## Architecture

Two services, two images, one persistent volume. The browser only ever talks to Nginx; the API is never exposed to the host.

```text
Windows browser
   │
   │  SSH tunnel  (127.0.0.1:18082  →  guest 127.0.0.1:8082)
   ▼
Ubuntu VM
   ┌───────────────────────────────────────────────────────┐
   │  Docker network (internal)                            │
   │                                                       │
   │   web  (nginx:1.28-alpine, digest-pinned)             │
   │     ├── /            static files from frontend/      │
   │     ├── /static/     CSS + JS                         │
   │     ├── /api/*    ──► api:5001                        │
   │     └── /health/* ──► api:5001                        │
   │                        │                              │
   │                   api  (python:3.14-slim,             │
   │                         digest-pinned, UID 10001)     │
   │                        │  Gunicorn, 2 workers         │
   │                        ▼                              │
   │                   named volume `data` → /data         │
   │                   (10001:10001, mode 0700)            │
   │                        └── opsdesk.sqlite3 (0600)     │
   └───────────────────────────────────────────────────────┘
        only published port: 127.0.0.1:8082 → web:80
```

Nginx resolves the API through Docker's embedded DNS (`resolver 127.0.0.11 valid=5s ipv6=off`) rather than a hard-coded container IP, so the API can be recreated on a new address without a restart of the proxy. Anything that is not `/`, `/index.html`, `/static/`, `/api/` or `/health/` returns 404 — the proxy does not fall through to the backend.

---

## Container hardening

These are enforced in the committed Dockerfiles and Compose file, not documented intentions:

- **Non-root application process.** `Dockerfile.api` creates a system user `opsdesk` at UID/GID `10001` and ends with `USER 10001:10001`. Verified inside a running container.
- **Locked-down data directory.** `/data` and `/app/instance` are `chown 10001:10001` and `chmod 700`. The API starts under `umask 077`, so the SQLite file is created `0600`. Verified: `drwx------ 1 10001 10001 /data` and `-rw------- 1 10001 10001 opsdesk.sqlite3`.
- **Digest-pinned base images.** Both Dockerfiles pin `@sha256:…` rather than a floating tag, so a build is reproducible and a base-image update is an explicit, reviewable change.
- **`no-new-privileges=true`** on both services, blocking setuid escalation.
- **Named volume for persistence.** Data survives `docker compose down`, rebuilds and image updates; the container filesystem holds nothing worth keeping.
- **Healthcheck-gated startup.** `web` declares `depends_on: api: condition: service_healthy`, so Nginx does not start until `/health/ready` passes 12 retries at 5s intervals.
- **Loopback-only publishing.** The single published port is bound to `127.0.0.1:8082`, so the stack is unreachable from the VM's network interface. Access from Windows goes through an SSH tunnel.
- **Allowlist `.dockerignore`.** It excludes everything and re-includes only the directories a build needs, so local databases, virtual environments and editor files cannot leak into an image layer.

---

## CI/CD

Two workflows run on every push and pull request to `main`.

### `ci.yml` — build and verify

| Job | Steps |
| --- | --- |
| **Backend tests** | Install fully pinned dependencies → record the resolved versions → run the pytest suite |
| **Container images** | Build both images → start them on a private Docker network → smoke-test readiness, the summary endpoint, static assets and 404 behaviour → tear the containers down |

The smoke test runs against real containers, not mocks: it asserts the process identity is UID `10001`, that `/data` is `drwx------`, and that the database file is `-rw-------`.

### `security.yml` — scan

| Job | Tool | Enforcement |
| --- | --- | --- |
| **Secret scanning** | gitleaks 8.30.1 over the **full history** (`fetch-depth: 0`) | **Blocking** |
| **Dependency audit** | pip-audit 2.10.1 against all three pin files | **Blocking** |
| **Container scanning** | Trivy 0.76.2: Dockerfile misconfiguration + both built images | Report-only baseline |

Scanners are installed by exact-version download URL and verified against a recorded SHA-256 checksum before use, with no `sudo`. The workflow also runs on a weekly schedule, because pinned dependencies do not change on their own but new advisories against them do. Trivy reports are written into the job summary and uploaded as an artefact.

**Why the split between blocking and report-only?** Secret leaks and vulnerable pins are mine to fix immediately, so they fail the build. Container findings need triage against a known baseline first; failing on day one would produce a permanently red build that teaches nothing. Enforcement is added per finding once it is understood.

---

## Project layout

```text
.
├── backend/
│   ├── opsdesk/          Flask application factory, schema, database access
│   ├── tests/            pytest suite
│   ├── requirements.in   Declared runtime dependencies
│   ├── requirements.txt  Fully resolved runtime pins
│   └── requirements-server.txt   Adds Gunicorn for the deployed image
├── frontend/
│   ├── index.html
│   └── static/           app.js, style.css
├── deploy/manual/        Systemd unit + host Nginx config for a non-container deploy
├── .github/workflows/    ci.yml, security.yml
├── Dockerfile.api        Gunicorn + Flask, non-root
├── Dockerfile.web        Nginx serving the static frontend
├── nginx-container.conf  Reverse proxy configuration
├── compose.yaml          Two services, named volume, healthcheck
├── run_local.py          Single-process loopback development convenience
└── .dockerignore         Allowlist build context
```

---

## Running it locally

Prerequisites: Docker Engine with the Compose plugin.

```bash
git clone https://github.com/kennethikugbe/opsdesk.git
cd opsdesk

docker compose up --build -d
docker compose ps                       # api should report (healthy)

curl http://127.0.0.1:8082/health/ready
curl http://127.0.0.1:8082/api/summary
```

Then open `http://127.0.0.1:8082/` in a browser on the same machine.

To reach the stack from another machine on the host — for example a Windows browser talking to a Linux VM — tunnel to the loopback port rather than publishing it on an interface:

```bash
ssh -N -L 18082:127.0.0.1:8082 user@vm-host
```

Persistence check:

```bash
docker compose down
docker compose up -d
curl http://127.0.0.1:8082/api/summary   # tickets from before the rebuild are still present
```

### Without containers

`deploy/manual/` contains a systemd unit and a host Nginx configuration for running the same code as two host services instead. `run_local.py` is a development shortcut that serves the frontend and API from one loopback-only process; it is **not** the separated deployment.

---

## Known limitations and what's next

This section is deliberate. Recording what is not yet true is part of the work.

**Open security findings.** Trivy reports `DS-0002` (HIGH) against `Dockerfile.web`: the Nginx image runs its master process as root in order to bind port 80. Fixing it means moving to an unprivileged listen port, adding a `USER` directive, and updating the proxy configuration and the Compose port mapping together — a change that needs a full rebuild test before it lands. `DS-0026` (LOW) notes the absence of an image-level `HEALTHCHECK`; the API is partly mitigated by a Compose-level healthcheck, but an image-level check would also protect a plain `docker run`. Base-image vulnerability findings from the report-only scan are pending triage.

**Not implemented.** There is no authentication, authorisation, TLS or rate limiting. SQLite is single-writer and unsuitable for concurrent load; `backend/opsdesk/db.py` talks to `sqlite3` directly, so a PostgreSQL migration means changing the data-access layer, not just a connection string. The Compose file is not assessed by `trivy config`, which detects only the two Dockerfiles.

**Planned.** PostgreSQL with a practised migration and recovery path · Ansible for repeatable server configuration · Terraform against an isolated local provider · monitoring, alerting and backup/restore verification.

**Safety boundary.** This is a local lab using fictional data. Do not expose the running application publicly, forward its port to a network interface, or deploy it to a cloud provider until the missing security controls above are addressed.

---

## Licence

MIT — see [LICENSE](./LICENSE). © 2026 Kenneth Ikugbe.
