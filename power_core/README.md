# power_core — Backend Processing Pipeline

Internal Flask service that ingests, processes, and enriches cycling activity data (.FIT files). Deployed on Google Cloud Run (private, no public access).

## Pipeline Stages

The `ActivityProcessingPipeline` class (`workshop/workers.py`) orchestrates the full workflow:

```
┌─────────────┐
│  1. Source  │  Dropbox sync (webhook) or Pub/Sub message from frontend
└──────┬──────┘
       ▼
┌─────────────┐
│ 2. Download │  .FIT file downloaded from Dropbox or received as bytes
└──────┬──────┘
       ▼
┌─────────────┐
│ 3. Decode   │  .FIT → CSV (unexplored) using fit2gpx & fitdecode
└──────┬──────┘
       ▼
┌─────────────┐
│ 4. Clean    │  GPS data cleaning — fix bad coordinates, detect bike model
└──────┬──────┘
       ▼
┌─────────────┐
│ 5. Encode   │  Clean CSV → clean .FIT, upload to GCS
└──────┬──────┘
       ▼
┌─────────────┐
│ 6. Strava   │  Upload cleaned activity to Strava with correct gear
└──────┬──────┘
       ▼
┌─────────────┐
│ 7. Heatmap  │  Composite GPX heatmap via GCS object compose
└──────┬──────┘
       ▼
┌─────────────┐
│ 8. PostGIS  │  Store track points in PostgreSQL for spatial queries
└─────────────┘
```

## Two Pipeline Modes

### Private Pipeline
- Triggered by a Dropbox webhook at the `/q50WoEoBoHoOoOoK0iBa216SztNO5R6c2vK0tb` endpoint
- Syncs .FIT files from the Dropbox `/apps/activities` folder
- Full processing: clean → Strava upload → heatmap → database
- Uses original filenames

### Public Pipeline (User Uploads)
- Triggered by Pub/Sub messages from the `site_handler` frontend
- Processes user-uploaded .FIT files
- Cleaned files stored in a public output bucket
- Results emailed to the user via a short-lived signed download link
- Uses UUID-based filenames to prevent collisions

## Project Structure

| Path | Purpose |
|------|---------|
| `power_core/main.py` | Flask app factory, registers blueprints |
| `power_core/routes/transfer.py` | HTTP endpoints (Dropbox webhook, Pub/Sub handlers, upload trigger) |
| `power_core/routes/pubsub_handler.py` | Pub/Sub message dispatching logic |
| `power_core/dropbox_usage/` | Dropbox authentication, file listing/syncing, uploads |
| `power_core/strava/` | Strava auth (token refresh) and activity upload |
| `power_core/workshop/workers.py` | `ActivityProcessingPipeline` — main pipeline orchestrator |
| `power_core/workshop/instruments.py` | FIT↔CSV conversion, GPS cleaning, email templating |
| `power_core/heatmap_gpx/` | GPX heatmap composition (GCS compose + Firestore state tracking) |
| `power_core/database/` | PostgreSQL connection and streaming COPY insert (dbt project included) |
| `power_core/postgis/` | FIT track point extraction for PostGIS ingestion |
| `power_core/utilites/email_sender.py` | SMTP & Brevo API email sending |
| `power_core/project_env/config.py` | Central environment variable loading |
| `power_core/templates/` | HTML email templates |

## Configuration

All configuration is loaded from environment variables at startup. Key variables:

| Variable | Description |
|----------|-------------|
| `GCP_PROJECT_ID` | GCP project ID |
| `GCS_BUCKET_NAME` | Internal processing bucket |
| `GCS_PUB_OUTPUT_BUCKET` | Public output bucket for user downloads |
| `DROPBOX_TOPIC_NAME` | Pub/Sub topic for Dropbox sync triggers |
| `GCP_TOPIC_NAME` | Pub/Sub topic for user upload messages |
| `STRAVA_UPLOAD` | `enable`/`disable` toggle for Strava upload |
| `PG_HOST` / `PG_USER` / `PG_PASS` / `PG_DATABASE` | PostgreSQL connection |

Secrets (Strava tokens, Dropbox tokens, service account keys) are loaded via Google Secret Manager at startup.

## Local Development

### Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager (replaces pip/venv)
- **Podman** (or Docker) — for the Secret Manager emulator
- **Java JRE 21** (optional) — only needed if running FIT→CSV conversion locally (`FitCSVTool.jar`)

### Quick Start

```bash
# 1. Create venv and install all dependencies (including gcp_actions editable)
cd power_core
uv venv
uv pip install -e .

# 2. Start the Secret Manager emulator
./local_dev.sh start

# 3. Export emulator connection vars
export SECRET_MANAGER_EMULATOR_HOST=localhost:8083
export GCP_PROJECT_ID=local-test-project

# 4. Run the app
.venv/bin/python power_core/main.py
```

### Project Dependencies

Dependencies are declared in `pyproject.toml` (not `requirements.txt` — that file is deprecated).
Key packages:

| Package | Purpose |
|---------|---------|
| `flask`, `gunicorn` | Web framework & WSGI server |
| `gcp-actions` (editable, from `../../gcp_actions`) | Shared GCP helper library |
| `google-cloud-*` | Firestore, Storage, Pub/Sub, Secret Manager |
| `dropbox` | Dropbox API (file sync) |
| `psycopg[binary]` | PostgreSQL connection |
| `fit2gpx`, `fitdecode` | FIT file parsing |
| `sib-api-v3-sdk` | Brevo (Sendinblue) email API |

### Architecture Note

`gcp_actions` is a **separate repository** (`/home/stas/projects/main/gcp_actions/`) —
it is NOT inside the `BigBikeData` folder. The `pyproject.toml` references it via a
relative editable path (`../../gcp_actions`). This is why `pip install -r requirements.txt`
alone will NOT work — you must use `uv pip install -e .` which resolves the path dependency.

### Secret Manager Emulator

Instead of a real `keys.env` file on disk (security risk), local development uses a
lightweight Secret Manager emulator. The emulator is a Flask app containerized with Podman.

```bash
./local_dev.sh start     # build image, start container, seed secrets (if keys.env found)
./local_dev.sh stop      # stop and remove container
./local_dev.sh seed      # re-seed secrets into a running emulator
./local_dev.sh env       # print export commands for your shell
```

**How it works:**
1. `local_dev.sh start` builds and runs the emulator container with `--network host`
2. If a `keys.env` file is found (checked in multiple locations), secrets are seeded
   into the emulator via its REST API
3. The app reads secrets from the emulator at `localhost:8083` — same API as production
   Secret Manager, just no GCP credentials needed

> **Note:** `keys.env` is a transient file. Once secrets are loaded into the emulator,
> the file can be deleted. The seed step skips gracefully if no `keys.env` is found.

## Troubleshooting

### `ModuleNotFoundError: No module named 'power_core'`

The `power_core` package must be installed as editable. Run:
```bash
uv pip install -e .
```
This is needed because `main.py` uses absolute imports like `from power_core.routes.transfer import ...`.

### `ImportError: cannot import name 'storage' from 'google.cloud'`

`gcp_actions` optional dependencies (storage, firestore, pubsub, secretmanager) are
not installed. Use `uv pip install -e .` — the `pyproject.toml` declares all needed extras.

### `FileNotFoundError: keys.env`

The seed step in `local_dev.sh` looks for `keys.env` in multiple locations. If not found,
it prints a warning and continues — the emulator may already have secrets from a previous run.
To seed fresh secrets, create a `keys.env` file and run `./local_dev.sh seed`.

### `Error: context must be a directory: ".../BigBikeData/gcp_actions/..."`

Path resolution bug — `gcp_actions` is a sibling of `BigBikeData`, not a child.
Check that `local_dev.sh`, `compose.yaml`, and `pyproject.toml` all use
`../../gcp_actions/...` (two levels up), not `../gcp_actions/...`.

### Podman port forwarding issues with POST requests

Rootless Podman's pasta networking has known issues with POST request forwarding.
The working setup uses `--network host` (see `local_dev.sh`), which avoids port
forwarding entirely. The `compose.yaml` is kept as a reference but `local_dev.sh`
uses bare `podman` commands for reliability.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/challenge` | GET | Dropbox webhook verification challenge |
| `/q50WoEoBoHoOoOoK0iBa216SztNO5R6c2vK0tb` | POST | Dropbox webhook (triggers sync) |
| `/pubsub-processing-handler` | POST | Public user upload processing (Pub/Sub push) |
| `/private-processing-handler` | POST | Private pipeline processing (Pub/Sub push) |
| `/<PRIVATE_UPLOAD_TOKEN>` | POST | Manual upload of GCS files to Dropbox |

## Deployment

Deployed with Google Cloud Build:

```bash
gcloud builds submit --config cloudbuild.yaml
```

The Dockerfile uses a multi-stage build with Java (for FitCSVTool.jar) and Python dependencies.
