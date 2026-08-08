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

## Configuration Architecture

Configuration comes from **three sources**, loaded in this order (later wins):

```
┌──────────────────────────────────────────────────────────┐
│ 1. Cloud Run env vars (4 pointers only)                  │
│    GCP_PROJECT_ID  APP_JSON_KEYS  SEC_DROPBOX            │
│    S_ACCOUNT_DROPBOX                                     │
├──────────────────────────────────────────────────────────┤
│ 2. Secret Manager (2 secrets, fetched at startup)        │
│    fullstack-app-json-keys  ← 28 config keys             │
│    dropbox-secrets          ←  8 Dropbox/Strava tokens   │
├──────────────────────────────────────────────────────────┤
│ 3. Firestore                                              │
│    config/local/settings/data  ← base config doc         │
│    db_cursor                  ← Dropbox sync cursor      │
├──────────────────────────────────────────────────────────┤
│ + local_config.json overrides (local dev, highest        │
│   priority — overrides everything above)                 │
└──────────────────────────────────────────────────────────┘
```

**The 4 pointer vars are the only env vars set directly.** They tell the app *which* secrets to fetch. Everything else — all 36+ config values and credentials — lives inside the two Secret Manager secrets.

### Secret: `fullstack-app-json-keys` (28 keys)

Loaded by `InjectConfig` at startup. Contains all general application configuration:

| Key | Category |
|-----|----------|
| `GCP_PROJECT_ID` | Project identity |
| `GCS_BUCKET_NAME`, `GCS_PUB_OUTPUT_BUCKET` | Storage buckets |
| `DROPBOX_TOPIC_NAME`, `GCP_TOPIC_NAME` | Pub/Sub topics |
| `CLOUD_RUN_SERVICE`, `CLOUD_RUN_SERVICE_PUB` | Cloud Run service names |
| `BREVO_API_KEY`, `SMTP_PASSWORD`, `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER` | Email (Brevo + SMTP) |
| `STRAVA_UPLOAD`, `EMAIL_MODE` | Feature toggles |
| `EVENTARC_SA`, `EVENTARC_TRIGGER` | Eventarc |
| `COOKIE_DOMAIN`, `FRONTEND_BASE_URL` | Web config |
| `PRIVATE_ACCESS_TOKEN`, `PRIVATE_UPLOAD_TOKEN` | Auth tokens |
| `S_ACCOUNT_RUN`, `S_ACCOUNT_DROPBOX` | Service account emails |
| `SEC_DROPBOX` | Pointer to Dropbox/Strava secret |
| `FLASK_SECRET_KEY` | Flask session signing |
| `BACKEND_TAG`, `FRONTEND_TAG` | Version tracking |
| `DONATION_HTML_SNIPPET_MONO`, `DONATION_HTML_SNIPPET_PRIVAT` | Donation UI |

### Secret: `dropbox-secrets` (8 keys)

Loaded by `DropboxAuth` on first webhook request. Contains OAuth tokens:

| Key | Note |
|-----|------|
| `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN` | Dropbox OAuth |
| `STRAVA_APP_ID`, `STRAVA_CLIENT_SECRET` | Strava OAuth |
| `STRAVA_REFRESH_TOKEN`, `STRAVA_ACCESS_TOKEN`, `EXPIRES_AT` | Strava tokens (refreshed at runtime) |

### `local_config.json` (local dev only)

Overrides any of the above + adds local-only PostgreSQL config:

```json
{
  "GCP_PROJECT_ID": "local-test-project",
  "APP_JSON_KEYS": "fullstack-app-json-keys",
  "SEC_DROPBOX": "dropbox-secrets",
  "S_ACCOUNT_DROPBOX": "local-dev@placeholder.iam.gserviceaccount.com",
  "S_ACCOUNT_RUN": "local-dev@placeholder.iam.gserviceaccount.com",
  "PG_HOST": "localhost",
  "DROPBOX_TOPIC_NAME": "dropbox-handler-testing",
  "LOGGING_LEVEL": "DEBUG"
}
```

## Local Development

### Prerequisites

- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager
- **Podman** — for the emulator containers
- **gocryptfs** — encrypted storage for secrets (`sudo apt install gocryptfs`)
- **Java JRE 21** (optional) — for FIT→CSV conversion (`FitCSVTool.jar`)

### Quick Start

```bash
# 1. Install dependencies
cd power_core
uv venv
uv pip install -e .

# 2. Start emulators (Secret Manager + encrypted volume)
./local_dev.sh start

# 3. Seed secrets (first time only — creates encrypted volume)
#    Put your keys.env in power_core/power_core/project_env/keys.env
./local_dev.sh seed

# 4. Run (env vars come from local_config.json automatically)
.venv/bin/python power_core/main.py
```

### Pre-flight Checks

The app validates configuration at **two levels** before accepting requests:

1. **`config.py` import time** — critical env vars must be set (`GCP_PROJECT_ID`, `APP_JSON_KEYS`, `SEC_DROPBOX`, `S_ACCOUNT_DROPBOX`, `S_ACCOUNT_RUN`). Missing → clear error with fix hints, exits immediately.

2. **`main.py` startup** — actually fetches each secret from the emulator (or real GCP) and verifies required keys exist in the payload. If the emulator wasn't seeded → error with instructions. Flask never starts with broken config.

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

### Secret Manager Emulator + Encrypted Volume

Local development uses a lightweight Secret Manager emulator (Flask in Podman).
Secrets are stored in a **gocryptfs-encrypted volume** — never plaintext on disk.

```
.emulator_data.enc/   ← encrypted ciphertext on disk (safe to commit? NO — still gitignored)
.emulator_data/       ← mounted decrypted view (in-memory via FUSE, gone on unmount)
```

**First run:**
```bash
./local_dev.sh start
# → generates encryption key → ~/.config/bigbikedata/emulator.key (chmod 600)
# → creates .emulator_data.enc/
# → mounts it, starts emulator, seeds from keys.env (if found)
```

**Every run after:**
```bash
./local_dev.sh start     # auto-mounts encrypted volume, emulator has all secrets
./local_dev.sh stop      # stops emulator + unmounts (secrets disappear from view)
```

**Key file:** `~/.config/bigbikedata/emulator.key` — keep this safe. Without it, the encrypted volume is unrecoverable.

```bash
./local_dev.sh start     # build image, start container, mount encrypted volume, seed if empty
./local_dev.sh stop      # stop container + unmount encrypted volume
./local_dev.sh seed      # re-seed secrets into a running emulator
./local_dev.sh env       # print export commands for your shell (DEPRECATED — local_config.json handles this)
```

### Ngrok Tunnel (Webhook Testing)

To test Dropbox webhooks locally, expose your local server to the internet via ngrok
running in a Podman container — no system install needed.

```bash
# Start with tunnel (requires ngrok authtoken)
NGROK_ENABLED=true ./local_dev.sh start

# Or just the tunnel (emulator already running)
NGROK_ENABLED=true ./local_dev.sh tunnel
```

**Prerequisites:**
- A free [ngrok account](https://dashboard.ngrok.com/signup) and authtoken
- Store the token in KDE Wallet: `kwallet-query` (the script auto-fetches it)
- Or export it directly: `export NGROK_AUTHTOKEN=your_token`

When the tunnel comes up, the script prints both the public URL and the full Dropbox
webhook URL ready to paste into the Dropbox App console:

```
[INFO]  Ngrok tunnel is LIVE
    Public URL:      https://xxxx-xxxx.ngrok-free.dev
    Dropbox webhook:  https://xxxx-xxxx.ngrok-free.dev/q50WoEoBoHoOoOoK0iBa216SztNO5R6c2vK0tb
```

The tunnel is stopped automatically with `./local_dev.sh stop`.

## Troubleshooting

### `ModuleNotFoundError: No module named 'power_core'`

The `power_core` package must be installed as editable:
```bash
uv pip install -e .
```

### `ModuleNotFoundError: No module named 'googleapiclient'`

Missing Pub/Sub dependency. Install:
```bash
uv pip install google-api-python-client
```

### `ImportError: cannot import name 'storage' from 'google.cloud'`

`gcp_actions` optional dependencies not installed. Use `uv pip install -e .` — `pyproject.toml` declares all needed extras.

### Pre-flight: `MISSING REQUIRED ENVIRONMENT VARIABLES`

Critical env vars not set. Each missing var gets a specific fix hint:
```
  • GCP_PROJECT_ID
    → export GCP_PROJECT_ID=local-test-project  (or ./local_dev.sh env)
  • APP_JSON_KEYS
    → add to local_config.json
```
Add them to `BigBikeData/local_config.json` or export in shell.

### Pre-flight: `Secret not found in emulator`

The emulator is running but doesn't have the secrets. Run:
```bash
./local_dev.sh seed    # requires keys.env with real tokens
```

### `FileNotFoundError: keys.env`

The seed step looks for `keys.env` in multiple locations. If not found, it skips —
the encrypted volume may already have secrets from a previous run.

### `Error: context must be a directory: ".../BigBikeData/gcp_actions/..."`

Path bug — `gcp_actions` is a sibling of `BigBikeData`, not a child. All paths must use
`../../gcp_actions/...` (two levels up), not `../gcp_actions/...`.

### Podman port forwarding issues with POST requests

Rootless Podman's pasta networking fails on POST. The fix is `--network host` (used by `local_dev.sh`).

### `gocryptfs: command not found`

Install: `sudo apt install gocryptfs`

### `AttributeError: 'NoneType' object has no attribute 'encode'` (Dropbox webhook)

`DROPBOX_APP_SECRET` is not configured — the `dropbox-secrets` secret is missing or has dummy data.
Seed real tokens: `./local_dev.sh seed`

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
