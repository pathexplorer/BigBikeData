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

```bash
# Set up virtual environment
cd power_core
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure local environment
cp ../local_config.json .   # or set env vars manually

# Run
python power_core/main.py
```

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
