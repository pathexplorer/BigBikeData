# power_core — Backend Processing Pipeline

Internal Flask service that ingests, processes, and enriches cycling activity data (.FIT files). Deployed on Google Cloud Run (private, no public access).

## Before You Start

This project depends on the **[gcp_actions](https://github.com/pathexplorer/gcp_actions)** library.
Both repos must be cloned **side-by-side** in the same parent directory:

```
~/projects/main/
├── BigBikeData/          ← this repo
│   ├── power_core/
│   ├── site_handler/
│   └── local_config.json ← already exists, pre-configured for local dev
└── gcp_actions/          ← library repo (clone separately)
    └── gcp_actions/
```

```bash
# 1. Clone both repos
git clone https://github.com/pathexplorer/BigBikeData.git
git clone https://github.com/pathexplorer/gcp_actions.git

# 2. Verify the layout
ls BigBikeData/power_core/pyproject.toml   # → must exist
ls gcp_actions/pyproject.toml              # → must exist
ls BigBikeData/local_config.json           # → pre-configured for local dev
```

> **Note:** `BigBikeData/local_config.json` already exists in the repo with sane defaults
> for local development. It is the **local equivalent of Cloud Run environment variables** —
> the same keys the app reads from the GCP environment in production are set here for local dev.
> You generally don't need to edit it unless you want to change port numbers or feature flags.

> 👉 **New here?** Jump straight to [Quick Start](#quick-start-step-by-step) to get the app running.
> The sections below (Pipeline, Architecture) are reference — come back when you need them.

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
- Triggered by a Dropbox webhook at a secret verification path (configured via `DROpbox_WEBHOOK_PATH` in secrets)
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

This file is the **local equivalent of Cloud Run environment variables**.
In production, the 4 pointer vars are set as Cloud Run env vars; locally,
`local_config.json` provides those same pointers + local-specific overrides
(emulator hosts, PostgreSQL host, feature flags).

```json
{
  "GCP_PROJECT_ID": "local-test-project",
  "SECRET_MANAGER_EMULATOR_HOST": "localhost:8083",
  "FIRESTORE_EMULATOR_HOST": "localhost:8085",
  "PUBSUB_EMULATOR_HOST": "localhost:8086",
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

Run these checks before starting. Every item must pass.

```bash
# 1. Python 3.12+
python --version
# → Python 3.12.x  (or newer)

# 2. uv package manager
uv --version
# → uv 0.x.x
# Install: curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Podman (for emulator containers)
podman --version
# → podman version 4.x.x  (or newer)

# 4. gocryptfs (for encrypted secrets volume)
gocryptfs -version 2>/dev/null || echo "NOT INSTALLED"
# Install: sudo apt install gocryptfs

# 5. Ports must be free
ss -tln | grep -E '808[1356]' && echo "⚠️  Port conflict!" || echo "✅ Ports 8081,8083,8085,8086 are free"

# 6. GCP project with required services enabled
#    (Firestore, Secret Manager, Cloud Storage, Pub/Sub)
gcloud config get-value project
# → your-project-id  (must be set)

# 7. Java JRE 21 (only needed for FIT→CSV conversion)
java -version 2>&1 | head -1

# 8. ngrok authtoken (required — real Dropbox webhooks are used in local dev)
#    Either set it in env, or store it in KDE Wallet under key 'ngrok':
#    export NGROK_AUTHTOKEN=your_token
```

### Quick Start (step by step)

**1. Install Python dependencies:**
```bash
cd power_core
uv venv
uv pip install -e .
```
> ⚠️ If this fails with a path error about `gcp_actions`, you forgot to clone the
> library repo. See [Before You Start](#before-you-start) — both repos must be siblings.

Expected: no errors. Verify with:
```bash
.venv/bin/python -c "import power_core; print('✅ power_core imported')"
.venv/bin/python -c "from gcp_actions.firestore_box.json_manipulations import FirestoreMagic; print('✅ gcp_actions imported')"
```

**2. Create `keys.env` (first time only):**

The `local_dev.sh start` script auto-detects this file and seeds the Secret Manager
emulator with it. Create it **before** starting the emulators:

```bash
# Minimal — just enough to start (dummy values):
cat > power_core/power_core/keys.env << 'EOF'
GCP_PROJECT_ID=local-test-project
FLASK_SECRET_KEY=dev-secret-key
S_ACCOUNT_RUN=local-dev@placeholder.iam.gserviceaccount.com
S_ACCOUNT_DROPBOX=local-dev@placeholder.iam.gserviceaccount.com
EOF
```

Replace with real tokens when you need Dropbox sync, Strava upload, or email sending.
For the full list of available keys, see the [keys.env template](#keysenv-format--copy-this-template-and-fill-in-your-values) below.

**3. Start emulators:**
```bash
# Pull real Firestore config from GCP + seed Secret Manager from keys.env:
./local_dev.sh start --from-gcp
```
One command does everything:
- Builds & starts the emulator containers (Secret Manager on :8083, Firestore on :8085, Pub/Sub on :8086)
- Mounts the encrypted volume for secrets
- Starts the **ngrok tunnel** (default) so Dropbox can deliver real webhooks
- `--from-gcp`: pulls `config/local/settings/data` from your real GCP Firestore
- Auto-seeds Secret Manager from `keys.env` (if found)

Expected output ends with:
```
[INFO]  ------------------------------------------------------
[INFO]  All emulators are running.
[INFO]
[INFO]    ✅ Secret Manager  : localhost:8083
[INFO]    ✅ Firestore        : localhost:8085
[INFO]    ✅ Pub/Sub          : localhost:8086
[INFO]    ✅ Encrypted volume : mounted
[INFO]
[INFO]  Next: run the app (step 4).
[INFO]  ------------------------------------------------------
```

**3. Verify emulators are working:**
```bash
# Secret Manager — health check
curl http://localhost:8083/health
# → {"emulator":"secret-manager","status":"ok"}

# Firestore — read the seeded document
FIRESTORE_EMULATOR_HOST=localhost:8085 python -c "
from google.cloud import firestore
db = firestore.Client()
doc = db.collection('config').document('local').collection('settings').document('data').get()
if doc.exists:
    print('✅ Firestore OK —', len(doc.to_dict()), 'keys')
else:
    print('❌ Document missing')
"
```

> 💡 If you ran `./local_dev.sh start --from-gcp` in step 3, the Firestore
> document should already contain your production keys (not the 6 placeholders).

**4. Run the app:**
```bash
.venv/bin/python power_core/main.py
```

**5. Stop everything when done:**
```bash
./local_dev.sh stop
# → stops pod + unmounts encrypted volume
```

### `keys.env` reference

If you need to re-seed or add real tokens later:

```bash
./local_dev.sh seed
```

**Full `keys.env` template** (all keys, for reference):
```bash
# ============================================================
# Secret: fullstack-app-json-keys  (general app configuration)
# ============================================================

# Required for the app to start:
GCP_PROJECT_ID=local-test-project
FLASK_SECRET_KEY=any-random-string-here
S_ACCOUNT_RUN=local-dev@placeholder.iam.gserviceaccount.com
S_ACCOUNT_DROPBOX=local-dev@placeholder.iam.gserviceaccount.com

# Required for the private pipeline (Dropbox + Strava):
SEC_DROPBOX=dropbox-secrets
GCS_BUCKET_NAME=your-bucket-name
DROPBOX_TOPIC_NAME=dropbox-handler-testing
GCP_TOPIC_NAME=pubsub-topic-name
CLOUD_RUN_SERVICE=power-core
CLOUD_RUN_SERVICE_PUB=power-core-public

# Email (Brevo or SMTP) — needed to send results to users:
EMAIL_MODE=brevo
BREVO_API_KEY=your-brevo-api-key
SMTP_PASSWORD=your-smtp-password
SMTP_SENDER=sender@example.com
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
SMTP_USER=your-smtp-user

# Feature toggles:
STRAVA_UPLOAD=false

# Optional — web frontend config (only needed for site_handler):
COOKIE_DOMAIN=localhost
FRONTEND_BASE_URL=http://localhost:5000
PRIVATE_ACCESS_TOKEN=some-token
PRIVATE_UPLOAD_TOKEN=some-upload-token

# Optional — Eventarc triggers:
EVENTARC_SA=
EVENTARC_TRIGGER=

# Optional — donation UI (can be empty):
DONATION_HTML_SNIPPET_MONO=
DONATION_HTML_SNIPPET_PRIVAT=

# Optional — version tags:
BACKEND_TAG=dev
FRONTEND_TAG=dev

# Optional — storage buckets (public pipeline):
GCS_PUB_OUTPUT_BUCKET=local-output-bucket

# ============================================================
# Secret: dropbox-secrets  (OAuth tokens)
# ============================================================

# Required for Dropbox webhook + file sync:
DROPBOX_APP_KEY=your-dropbox-app-key
DROPBOX_APP_SECRET=your-dropbox-app-secret
DROPBOX_REFRESH_TOKEN=your-dropbox-refresh-token

# Required for Strava upload:
STRAVA_APP_ID=your-strava-app-id
STRAVA_CLIENT_SECRET=your-strava-client-secret
STRAVA_REFRESH_TOKEN=your-strava-refresh-token
STRAVA_ACCESS_TOKEN=your-strava-access-token
STRAVA_EXPIRES_AT=0
```

### How configuration flows at startup

When you run `power_core/main.py`, `InjectConfig.load_and_inject_config()` executes:

```
1. Firestore emulator (localhost:8085)
   └─ Reads config/local/settings/data → base config dict (6 keys)

2. local_config.json (BigBikeData/local_config.json)
   └─ Overrides + adds keys (APP_JSON_KEYS, SEC_DROPBOX, PG_HOST, etc.)

3. Secret Manager emulator (localhost:8083)
   └─ Fetches fullstack-app-json-keys (28 keys) + dropbox-secrets (8 keys)
   └─ Merged on top of Firestore/local defaults

4. local_config.json — applied AGAIN
   └─ Local overrides win over everything (highest precedence)

5. All keys injected into os.environ
```

Key takeaway: you only need to configure two things:
- **`keys.env`** — real tokens/secrets (seeded once into the encrypted volume)
- **`local_config.json`** — local overrides (port numbers, project ID, feature flags)

Everything else comes from the emulators automatically.

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

### Firestore Emulator

The Firestore emulator provides the `config/local/settings/data` document used by
`InjectConfig` at startup. It runs as a container inside the same podman pod.
Data is stored **in memory** — lost on stop. Re-seed with `./local_dev.sh start --from-gcp`
after each restart.

**Two ways to populate it:**

#### 1. Pull from GCP (the standard workflow)

```bash
# One command — starts emulators AND pulls real GCP config:
./local_dev.sh start --from-gcp

# Or manually if emulators are already running:
gcloud auth application-default login   # one-time
FIRESTORE_EMULATOR_HOST=localhost:8085 \
    python ../gcp_actions/gcp_actions/emulators/firestore/seed.py --from-project
```

This reads the exact same document the production app uses and seeds it locally.
Add `--defaults-json` to override specific keys for local dev:

```bash
FIRESTORE_EMULATOR_HOST=localhost:8085 \
    python ../gcp_actions/gcp_actions/emulators/firestore/seed.py \
    --from-project my-real-gcp-project \
    --defaults-json '{"LOGGING_LEVEL":"DEBUG"}'
```

#### 2. Placeholder defaults (what `local_dev.sh start` seeds before you pull)

`./local_dev.sh start` seeds these 6 placeholder keys so the emulator isn't
empty on first run. They are overwritten when you run `--from-project` above.

| Key | Default value |
|---|---|
| `CS_BUCKET_NAME` | `local-dev-bucket` |
| `EMAIL_MODE` | `brevo` |
| `GCS_PUB_INPUT_BUCKET` | `local-input-bucket` |
| `GCS_PUB_OUTPUT_BUCKET` | `local-output-bucket` |
| `DROPBOX_TOPIC_NAME` | `dropbox-handler-testing` |
| `LOGGING_LEVEL` | `DEBUG` |

Default values can be customized in `local_config.json` (which takes highest precedence).

### Pub/Sub Emulator

`./local_dev.sh start` also starts a **Pub/Sub emulator** inside the pod
(`bigbikedata-ps-emulator`, published on `localhost:8086`). It uses the same
`google/cloud-sdk:emulators` image as Firestore.

The pipeline's `publish_to_pubsub` step (used by the Dropbox sync flow) needs a
Pub/Sub endpoint locally. Previously the Pub/Sub emulator had to be started
**manually** and was NOT attached to the pod — which made the pipeline fail.
Now it is a first-class emulator started automatically.

On startup the script also **auto-creates the topic + push subscription** so the
pipeline works end-to-end without manual steps:

- **Topic:** `DROPBOX_TOPIC_NAME` from `local_config.json` (default `dropbox-handler-testing`)
- **Subscription:** `local-processing-sub`
- **Push endpoint:** `http://localhost:8081/private-processing-handler` (the local backend)

The app connects to the emulator via `PUBSUB_EMULATOR_HOST` (added to
`local_config.json`), which routes the gRPC Pub/Sub client to the emulator.

Configurable via env vars (defaults shown):
```bash
PUBSUB_EMULATOR_HOST=127.0.0.1:8086
PUBSUB_TOPIC_NAME=dropbox-handler-testing
PUBSUB_SUBSCRIPTION_NAME=local-processing-sub
PUBSUB_PUSH_ENDPOINT=http://localhost:8081/private-processing-handler
```

> **Note:** The topic/subscription setup and Firestore seeding run with the
> project's venv python (`.venv/bin/python`) because they import `google.cloud.*`
> which is not installed in the system python. `local_dev.sh` detects the venv
> automatically. A seeding failure is non-fatal and won't block the emulators
> or the ngrok tunnel from starting.

### Pod Architecture

All emulators run inside a single **podman pod** (`bigbikedata-dev`).
Ports are published on the pod — defined once, not per-container:

```
┌─────────────────────────────────────────┐
│  Pod: bigbikedata-dev                   │
│                                         │
│  ┌─────────────────────────────────┐    │
│  │ sm-emulator  (port 8083)        │    │
│  │ fs-emulator  (port 8085)        │    │
│  │ ps-emulator  (port 8086)        │    │
│  │  ↕ localhost (shared namespace) │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

| Service | Host port | Container |
|---|---|---|
| Secret Manager emulator | `localhost:8083` | `bigbikedata-sm-emulator` |
| Firestore emulator | `localhost:8085` | `bigbikedata-fs-emulator` |
| Pub/Sub emulator | `localhost:8086` | `bigbikedata-ps-emulator` |
| Ngrok tunnel (local target) | `localhost:8081` | `bigbikedata-ngrok` |

### Ngrok Tunnel (Webhook Testing)

✅ **Ngrok runs by default** on `./local_dev.sh start`. This is because local
development uses the **real Dropbox API + real webhook delivery** — Dropbox
cannot reach `localhost`, so a public tunnel is required for the Dropbox webhook
to trigger the sync.

- **Default (recommended):** `./local_dev.sh start` starts the tunnel. It needs
  an ngrok authtoken (from env or KDE Wallet — see below). When it comes up it
  prints the public URL + Dropbox webhook URL to paste into the Dropbox App
  console.
- **Disable (only if you use a Dropbox mock instead of real webhooks):**
  ```bash
  NGROK_ENABLED=false ./local_dev.sh start
  ```

To **start** the tunnel explicitly (emulators already running):
```bash
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
    Dropbox webhook:  https://xxxx-xxxx.ngrok-free.dev/<DROpbox_WEBHOOK_PATH>
```

The tunnel is stopped automatically with `./local_dev.sh stop`.

## Troubleshooting

### `ModuleNotFoundError: No module named 'power_core'`

The `power_core` package must be installed as editable:
```bash
uv pip install -e .
```

### `ModuleNotFoundError: No module named 'googleapiclient'`

This old error happened because local dev used the HTTPS Pub/Sub client (which
needs `googleapiclient`). With the Pub/Sub emulator running (and
`PUBSUB_EMULATOR_HOST` set), local dev now uses the gRPC client against the
emulator — so `googleapiclient` is no longer required for the local path.

If you still see it, make sure the Pub/Sub emulator is running on the pod and
that `PUBSUB_EMULATOR_HOST` is in `local_config.json`, then restart:
```bash
./local_dev.sh start
uv pip install -e .
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

Rootless Podman's pasta networking can fail on POST with bridge networking.
The `local_dev.sh` script uses a **pod** for the emulators and `--network host`
for the ngrok container to avoid this issue.

### `gocryptfs: command not found`

Install: `sudo apt install gocryptfs`

### `AttributeError: 'NoneType' object has no attribute 'encode'` (Dropbox webhook)

`DROPBOX_APP_SECRET` is not configured — the `dropbox-secrets` secret is missing or has dummy data.
Seed real tokens: `./local_dev.sh seed`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/challenge` | GET | Dropbox webhook verification challenge |
| `/<DROpbox_WEBHOOK_PATH>` | POST | Dropbox webhook (triggers sync) |
| `/pubsub-processing-handler` | POST | Public user upload processing (Pub/Sub push) |
| `/private-processing-handler` | POST | Private pipeline processing (Pub/Sub push) |
| `/<PRIVATE_UPLOAD_TOKEN>` | POST | Manual upload of GCS files to Dropbox |

## Deployment

Deployed with Google Cloud Build:

```bash
gcloud builds submit --config cloudbuild.yaml
```

The Dockerfile uses a multi-stage build with Java (for FitCSVTool.jar) and Python dependencies.
