# GCP Project Bootstrap Script

This script automates provisioning a new GCP project for the **BigBikeData / power_core** application. It handles project creation, IAM, secrets, Pub/Sub, Artifact Registry, Cloud Run, and Firestore setup.

Supports **dual-environment provisioning**: `prod` (production) and `dev` (development).

## Prerequisites

- **Google Cloud SDK** (`gcloud`) installed and authenticated
- **Docker** installed (for Artifact Registry authentication)
- **Python virtual environment** activated with environment-specific `keys.env` file at `$VIRTUAL_ENV/../keys.env.{prod|dev}`

### Required environment variables (`keys.env.prod` or `keys.env.dev`)

| Variable                       | Description                                      |
|--------------------------------|--------------------------------------------------|
| `REGION`                       | GCP region (e.g. `us-central1`)                  |
| `MY_USER_ACCOUNT`              | Your email (used for IAM binding)                |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the service account JSON key file      |
| `GCONFIG_NAME`                 | Name for the gcloud configuration                |
| `SA_NAME_DROPBOX`              | Dropbox service account name (base, `-dev` added automatically) |
| `SA_NAME_STRAVA`               | Strava service account name (base, `-dev` added automatically) |
| `SA_NAME_RUN`                  | Main Cloud Run service account name (base, `-dev` added automatically) |
| `SEC_DROPBOX`                  | Secret name for Dropbox credentials (base, `-dev` added automatically) |
| `SEC_STRAVA`                   | Secret name for Strava credentials (base, `-dev` added automatically) |
| `ARTIFACT_REGISTRY`            | Artifact Registry repository name (base, `-dev` added automatically) |
| `GCP_TOPIC_NAME`               | Pub/Sub topic name (base, `-dev` added automatically) |
| `GCP_SUBSCRIPTION_NAME`        | Pub/Sub subscription name (base, `-dev` added automatically) |
| `CLOUD_RUN_SERVICE`            | Cloud Run service name for power_core (base, `-dev` added automatically) |
| `CLOUD_RUN_SERVICE_PUB`        | Cloud Run service name for site_handler (base, `-dev` added automatically) |

### Dropbox Setup (Required for Both Environments)

**Create TWO separate Dropbox Apps** in the [Dropbox Developer Console](https://www.dropbox.com/developers/apps):

| Environment | App Name | Folder Path | Purpose |
|-------------|----------|-------------|---------|
| Production  | `bigbikedata-prod` | `/apps/bigbikedata-prod` | Real user data |
| Development | `bigbikedata-dev` | `/apps/bigbikedata-dev` | Test data |

Each app needs:
1. **App Key** → `DROPBOX_APP_KEY`
2. **App Secret** → `DROPBOX_APP_SECRET`
3. **Refresh Token** → `DROPBOX_REFRESH_TOKEN` (generate via OAuth flow)

The credentials are stored in Secret Manager under `dropbox-secrets` (prod) and `dropbox-secrets-dev` (dev).

## Usage

```bash
source your-venv/bin/activate

# Provision production environment (default)
./start.sh prod

# Provision development environment
./start.sh dev

# Restart from scratch (clears progress log)
./start.sh prod reset
./start.sh dev reset
```

## What it does (stages)

| Stage | Name                  | Description                                         |
|-------|-----------------------|-----------------------------------------------------|
| 1     | Create Project        | Generates a project name and creates a new GCP project |
| 2     | Enable APIs           | Enables required GCP APIs (Secret Manager, Compute, Firestore, Cloud Run, Pub/Sub, Eventarc, etc.) |
| 3     | Config & Project Info | Creates a gcloud configuration, stores project number |
| 4     | Create Main Bucket    | Creates the primary GCS bucket for the project     |
| 4b    | Create Public Buckets | Creates public input/output buckets for user uploads |
| 4c    | Create Build Bucket   | Creates Cloud Build staging bucket                 |
| 5     | Create Service Accounts | Creates Dropbox, Strava, and Run service accounts (with `-dev` suffix for dev env) |
| 6     | Create Secrets        | Creates secrets in Secret Manager for Dropbox and Strava (with placeholder values — see below) |
| 7     | Bind IAM Roles        | Assigns roles to SAs, compute engine, and user account; grants impersonation roles; verifies secret access bindings |
| 8     | Pub/Sub Setup         | Creates Pub/Sub topic, dead-letter topic, and subscription with DLQ policy |
| 9     | Artifact Registry     | Creates a Docker repository and configures Docker auth |
| 11    | JSON Credentials      | Downloads a key file for the Run service account    |
| 12    | Create Firestore      | Creates a Firestore database in the specified region |

> Stage 10 is omitted intentionally — numbering matches the original deployment plan.
> Stage 6 (secrets) intentionally runs **before** Stage 7 (IAM binding + verification), because the access verification in Stage 7 reads the secrets and binding roles requires the secrets to already exist. If you have an old `script_progress.log`, remove it (or re-run with `reset`) so the renumbered stages take effect.

## Environment-Specific Behavior

### Production (`prod`)
- Uses base names from `keys.env.prod` (e.g., `SA_NAME_DROPBOX=bike-dropbox`)
- Creates project with generated name (e.g., `bigbikedata-prod-xyz123`)
- All resources use base names

### Development (`dev`)
- Uses base names from `keys.env.dev` (e.g., `SA_NAME_DROPBOX=bike-dropbox`)
- Automatically appends `-dev` suffix to all resource names:
  - Service accounts: `bike-dropbox-dev`, `bike-strava-dev`, `bike-run-dev`
  - Secrets: `dropbox-secrets-dev`, `strava-secrets-dev`
  - Artifact Registry: `bigbikedata-docker-dev`
  - Pub/Sub: `pubsub-topic-dev`, `pubsub-subscription-dev`
  - Cloud Run services: `power-core-dev`, `site-handler-dev`
  - **Storage buckets**: All buckets get `-dev` suffix (main, public input/output, build staging)
- Creates project with generated name (e.g., `bigbikedata-dev-xyz123`)
- Uses placeholder/test values for secrets (not production tokens)

## Progress tracking

The script writes a `script_progress_{env}.log` file to track completed stages per environment. If the script is interrupted, re-running it skips already-finished stages. Pass `reset` to clear the log and re-run everything.

## Output

A `names.env` file is generated containing:
- `GCP_PROJECT_ID` — the new project ID
- `GCP_PROJECT_NUMBER` — the numeric project number
- `GCP_BUCKET_NAME` — the created bucket name

Entries are appended only once per key, so re-runs do not duplicate them.

## Security notes

- **`keys.env.{prod|dev}` holds sensitive credentials in plaintext.** It contains the GCP service account key path and the secrets used to provision the Dropbox/Strava API tokens. It is recommended to protect it at rest (e.g., store an encrypted copy with `gpg`/`sops` and decrypt into a temporary file only when running) and to never commit it to version control.
- **Secrets are created with placeholder values.** Stage 6 stores `secret-data-for-app-1` and `secret-data-for-app-2` as the first secret versions so the project bootstraps end-to-end. After setup, replace them with the real Dropbox/Strava tokens via `gcloud secrets versions add`. This also means the access-binding verification in Stage 7 only proves *IAM access*, not the correctness of the token data.
- **Development environment**: Use test/placeholder tokens only. Never use production API credentials in the dev project.

## Extending

- Place reusable functions in `lib/*.sh`
- Place addon modules in `addons/*.sh`
