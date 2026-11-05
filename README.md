# OpsDesk — full-stack local learning project

OpsDesk is a support-ticket application designed for a hands-on DevOps and DevSecOps mentorship. A team can create requests with a title, fictional requester, category, priority and description; see summaries and filter requests; and update request status.

## What is already implemented

- **Frontend source:** a separate, static HTML/CSS/JavaScript interface in `frontend/`.
- **Backend source:** a Python/Flask JSON API in `backend/`, with liveness and readiness endpoints.
- **Database:** SQLite persistence for the initial local lab. In a later milestone of this same project, the mentor will adapt the API for PostgreSQL and we will practise migration and recovery.
- **Tests:** pytest API and separation tests in `backend/tests/`.
- **Local development convenience:** `run_local.py` serves the separate UI files and API from one loopback-only process. It is a quick testing mode, **not** the separate frontend/backend deployment.

**What is not built or deployed yet:** Dockerfiles, Docker Compose, GitHub Actions, Ansible playbooks, Terraform configurations, an Nginx deployment and a live Azure environment. You will build these with your mentor as part of the project, then push and deploy them yourself. No repository, VM, workflow or cloud resource is created by this ZIP.

## Important safety boundary

This is a **local-only, production-style learning project, not a production-ready service**. It has no authentication, authorisation, TLS, rate limiting or production server. Use fictional data only. Do not expose the running app publicly, forward its port to a network, or put it on Azure until missing security controls and architecture have been addressed.

For a private lab in a VirtualBox VM, keep application/reverse-proxy ports bound to the Ubuntu guest's loopback and access them from Windows through an SSH tunnel. This is a lab design, not a substitute for proper production identity and network controls.

## Target architecture to build together

```text
Windows browser
   │  SSH tunnel (private, local lab)
   ▼
Frontend service / reverse proxy (Nginx)
   ├── /static and /        → static HTML/CSS/JS in frontend/
   └── /api/* and /health/* → Flask backend service (Gunicorn)
                                  │
                                  ▼
                              SQLite data in a persistent volume
```

The browser uses **relative API URLs**, so it calls the same frontend origin. The reverse proxy will forward API and health paths to the backend internally; no browser code should point at a VM's `localhost` or a hard-coded container address. When we reach Docker, frontend and backend will have separate images/services; the existing SQLite data must be kept in a properly permissioned persistent volume. A single Flask app serving a UI can be a valid real-world design too—this split is chosen to practise independently deployable components.

## Planned DevOps work

1. Install Ubuntu Server in VirtualBox and connect from Windows using SSH.
2. Understand and test the application locally.
3. Use Git and GitHub to track reviewed source and configuration.
4. Create frontend and backend Dockerfiles and a Docker Compose deployment; keep its host-facing port on loopback and use an SSH tunnel. Validate persistence.
5. Build CI with GitHub Actions: tests, security checks and image builds, subject to current account quotas.
6. After the initial SQLite stack works, adapt the API to PostgreSQL and practise a database migration and recovery. This adaptation and the database service are not implemented yet.
7. Use Ansible from a Linux control environment to configure a disposable/local server and deploy the stack.
8. Practise Terraform on local-only resources; then write Azure infrastructure definitions. Do not apply Azure resources unless their cost and eligibility are verified and you approve.
9. Add monitoring, recovery and further security controls. Azure deployment is conditional on the strict zero-spend requirement.

A GitHub-hosted CI runner cannot reach a private VM at your computer's `127.0.0.1`. We will not expose your VM to the internet just to make CI deploy to it. Initially, CI can test a temporary stack in its own runner, while you deploy a reviewed version from inside your VM. Any self-hosted runner would need a separate security review.

If Terraform later manages local Docker resources, it will use its own isolated lab resources rather than simultaneously managing the same containers as Docker Compose. Terraform state can include secrets: keep state and real credentials out of Git.

## Local development check (after prerequisites are ready)

From the project root on Ubuntu/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
cd backend
../.venv/bin/python -m pytest -q
cd ..
.venv/bin/python run_local.py
```

Then visit `http://127.0.0.1:5000` **on the computer running the app**. When the app runs in an Ubuntu VM, a browser on Windows needs a properly configured SSH tunnel. Stop the server with `Ctrl+C`. This mode uses Flask's development server and is not for production.

To start only the API for development, run `python backend/run.py` using the virtual environment; it binds to guest loopback port 5000. Tests require Python 3.11 or newer. Installation downloads Python dependencies and may use internet data.

## Project structure

```text
opsdesk-fullstack/
├── frontend/                 # Static HTML, CSS and browser JavaScript
│   ├── index.html
│   └── static/
├── backend/                  # Flask API, SQLite schema and tests
│   ├── opsdesk/
│   ├── tests/
│   ├── run.py
│   └── requirements*.txt
├── run_local.py              # Local-only UI + API development convenience
└── .gitignore                # Excludes environments, local data and secrets
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api` | API identification |
| GET | `/health/live` | Process liveness |
| GET | `/health/ready` | Database table readiness; 503 on failure |
| GET | `/api/summary` | Counts by status |
| GET | `/api/tickets?status=all` | Up to 100 recent requests |
| GET | `/api/tickets/<id>` | Read one request |
| POST | `/api/tickets` | Create a request using JSON |
| PATCH | `/api/tickets/<id>` | Change status with JSON such as `{"status":"in_progress"}` |

The backend validates input and uses parameterised SQL, but the service is not authenticated. The starter schema is initialised at startup; it is not a migration system. Avoid committing `instance/`, virtual environments, credentials or real data. The `.gitignore` is helpful but you must still inspect each commit.
