# GCP Project Bootstrap Script

This script automates provisioning a new GCP project for the **BigBikeData / power_core** application. It handles project creation, IAM, secrets, Pub/Sub, Artifact Registry, Cloud Run, and Firestore setup.

## Prerequisites

- **Google Cloud SDK** (`gcloud`) installed and authenticated
- **Docker** installed (for Artifact Registry authentication)
- **Python virtual environment** activated with a `keys.env` file at `$VIRTUAL_ENV/../keys.env`

### Required environment variables (`keys.env`)

| Variable                       | Description                                      |
|--------------------------------|--------------------------------------------------|
| `REGION`                       | GCP region (e.g. `us-central1`)                  |
| `MY_USER_ACCOUNT`              | Your email (used for IAM binding)                |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the service account JSON key file      |
| `GCONFIG_NAME`                 | Name for the gcloud configuration                |
| `SA_NAME_DROPBOX`              | Dropbox service account name                     |
| `SA_NAME_STRAVA`               | Strava service account name                      |
| `SA_NAME_RUN`                  | Main Cloud Run service account name              |
| `SEC_DROPBOX`                  | Secret name for Dropbox credentials              |
| `SEC_STRAVA`                   | Secret name for Strava credentials               |
| `ARTIFACT_REGISTRY`            | Artifact Registry repository name                |
| `GCP_TOPIC_NAME`               | Pub/Sub topic name                               |
| `GCP_SUBSCRIPTION_NAME`        | Pub/Sub subscription name                        |

## Usage

```bash
source your-venv/bin/activate
./start.sh
```

To restart from scratch (clears progress log):

```bash
./start.sh reset
```

## What it does (stages)

| Stage | Name                  | Description                                         |
|-------|-----------------------|-----------------------------------------------------|
| 1     | Create Project        | Generates a project name and creates a new GCP project |
| 2     | Enable APIs           | Enables required GCP APIs (Secret Manager, Compute, Firestore, Cloud Run, Pub/Sub, Eventarc, etc.) |
| 3     | Config & Project Info | Creates a gcloud configuration, stores project number |
| 4     | Create Bucket         | Creates a GCS bucket for the project               |
| 5     | Create Service Accounts | Creates Dropbox, Strava, and Run service accounts |
| 6     | Bind IAM Roles        | Assigns roles to SAs, compute engine, and user account; grants impersonation and token creator roles |
| 7     | Create Secrets        | Creates secrets in Secret Manager for Dropbox and Strava |
| 8     | Pub/Sub Setup         | Creates Pub/Sub topic, dead-letter topic, and subscription with DLQ policy |
| 9     | Artifact Registry     | Creates a Docker repository and configures Docker auth |
| 11    | JSON Credentials      | Downloads a key file for the Run service account    |
| 12    | Create Firestore      | Creates a Firestore database in the specified region |

> Stage 10 is omitted intentionally — numbering matches the original deployment plan.

## Progress tracking

The script writes a `script_progress.log` file to track completed stages. If the script is interrupted, re-running it skips already-finished stages. Pass `reset` to clear the log and re-run everything.

## Output

A `names.env` file is generated containing:
- `GCP_PROJECT_ID` — the new project ID
- `GCP_PROJECT_NUMBER` — the numeric project number
- `GCP_BUCKET_NAME` — the created bucket name

## Extending

- Place reusable functions in `lib/*.sh`
- Place addon modules in `addons/*.sh`
