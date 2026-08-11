# GCP Project Bootstrap Script

This script automates provisioning a new GCP project for the **BigBikeData / power_core** application. It handles project creation, IAM, secrets, Pub/Sub, Artifact Registry, Cloud Run, and Firestore setup.

Supports **dual-environment provisioning**: `prod` (production) and `dev` (development).

## Quick Start (Interactive Welcome Phase)

**New users**: Just run the script! It will guide you through all required configuration interactively:

```bash
source your-venv/bin/activate

# Provision production environment (will prompt for all settings)
./start.sh prod

# Provision development environment (will prompt for all settings)
./start.sh dev
```

On first run, the **Welcome Phase** will:
1. Show a friendly introduction
2. Prompt for each required variable with descriptions and defaults
3. Offer to save your configuration to `keys.env.{prod|dev}` for future runs

### What you actually need to provide

**Only your Google account email** (an account with GCP + billing enabled). The script does
the rest:

- The following are **auto-generated** in Stage 0 — you never type them:
  - `SA_NAME_DROPBOX`, `SA_NAME_STRAVA`, `SA_NAME_RUN`, `EVENTARC_SA`
  - `SEC_DROPBOX`, `SEC_FULLSTACK_JSON_KEYS`
  - `ARTIFACT_REGISTRY`
  - `GCP_TOPIC_NAME`, `DROPBOX_TOPIC_NAME`, `DROPBOX_SUBSCRIPTION_NAME`, `EVENTARC_TRIGGER`
  - `CLOUD_RUN_SERVICE`, `CLOUD_RUN_SERVICE_PUB`
  - `GCS_BUCKET_NAME`, `GCS_PUB_OUTPUT_BUCKET`, `GCS_PUB_INPUT_BUCKET`, `GCS_BUILD_BUCKET`
- Authentication uses `gcloud auth application-default login` (ADC). `GOOGLE_APPLICATION_CREDENTIALS`
  is **optional** — only set it if you want Stage 11 to download a JSON key file for the Run SA.

## Prerequisites

- **Google Cloud SDK** (`gcloud`) installed and authenticated
- **Docker** installed (for Artifact Registry authentication)
- **Python virtual environment** activated (for environment file discovery)

### Environment file (`keys.env.{prod|dev}`)

The script reads `keys.env.{prod|dev}` located **next to your virtualenv** — i.e.
`$VIRTUAL_ENV/../keys.env.{env}` (for this project, `power_core/keys.env.{env}`). If the file
doesn't exist, the Welcome Phase creates/collects it for you. To prefill values, copy the
templates (`keys.env.prod.template` / `keys.env.dev.template` at the repo root) there.

> **Which variables do I need?** The complete registry is in
> [`config-manifest.md`](config-manifest.md) — every variable, which layer it
> lives in (keys.env / names.env / Secret Manager / Firestore), who consumes it,
> and a step-by-step checklist to build a new environment.

The only variable you truly must set is **`MY_USER_ACCOUNT`**:

| Variable            | Description                            | Default          |
|---------------------|----------------------------------------|------------------|
| `MY_USER_ACCOUNT`   | Your Google account email (required)   | –                |
| `REGION`            | GCP region                             | `us-central1`    |
| `GCONFIG_NAME`      | gcloud configuration name              | `power-core-{env}`|
| `ORG_PREFIX`        | Organization prefix                    | `bigbikedata`    |
| `APP_NAME`          | Application name                       | `power-core`     |
| `SA_DEPLOYER_EMAIL` | Deployer service account email (created by Stage 5b; only the name matters) | `bike-ci-deployer` |

### Dropbox & Strava Setup (Required for Both Environments)

**Create TWO separate Dropbox Apps** in the [Dropbox Developer Console](https://www.dropbox.com/developers/apps). Each environment uses a **separate Dropbox account**:

| Environment | App Name | App's own folder | Watched folder (Wahoo source) | Purpose |
|-------------|----------|------------------|-------------------------------|---------|
| Production  | `bigbikedata-prod` | `/apps/bigbikedata-prod` | `/apps/activities` | Real user data |
| Development | `bigbikedata-dev` | `/apps/bigbikedata-dev` | `/apps/activities` | Test data |

The watched folder `/apps/activities` is created by the Wahoo connection inside each account
(`Apps` is Dropbox's predefined per-app folder; `activities` is the single folder the user
renamed after connecting Wahoo). The app must be created as a **Scoped App with Full Dropbox
access** so it can read files outside its own folder. There must be exactly **one** watched
folder, and its path can be overridden per environment via `DROPBOX_WATCHED_FOLDER`.

Each app needs:
1. **App Key** → `DROPBOX_APP_KEY`
2. **App Secret** → `DROPBOX_APP_SECRET`
3. **Refresh Token** → `DROPBOX_REFRESH_TOKEN` (generate via OAuth flow)

**Strava credentials** are also stored in the same combined secret:
- **Client ID** → `STRAVA_CLIENT_ID`
- **Client Secret** → `STRAVA_CLIENT_SECRET`
- **Refresh Token** → `STRAVA_REFRESH_TOKEN`

The credentials are stored in Secret Manager under a **single combined secret** named `{org}-{env}-{app}-dropbox-secrets` (e.g., `bigbikedata-dev-power-core-dropbox-secrets`). This secret contains both Dropbox and Strava credentials.

Additionally, a separate secret **`fullstack-app-json-keys`** (`{org}-{env}-{app}-fullstack-app-json-keys`) is created for all other JSON key files (service account keys, etc.).

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

# Dry-run mode (no GCP changes)
./start.sh dev --dry-run

# Skip welcome phase (use existing keys.env only)
./start.sh prod --no-welcome

# Non-interactive: auto-approve generated names without prompting.
# Combine with --no-welcome and --dry-run for fully unattended runs (CI).
./start.sh prod --no-welcome --dry-run --yes
```

> **Non-interactive runs:** the name-approval prompt prints a resource table and, on EOF/non-interactive
> stdin, the script now **aborts** with a clear error instead of re-printing the table in an infinite loop.
> Use `--yes` to auto-approve, or feed `Y` on stdin (e.g. `printf 'Y\n' | ./start.sh prod --no-welcome`).

## Cleanup (Optional)

For CI/CD pipelines or failed runs, an optional cleanup script removes all created resources:

```bash
# Preview what would be deleted (safe)
./cleanup.sh dev --dry-run

# Interactive cleanup
./cleanup.sh dev

# Non-interactive (CI/CD)
./cleanup.sh prod --yes
```

The cleanup script:
- Deletes resources in reverse dependency order (subscriptions → topics, IAM bindings → SAs)
- Preserves the GCP project by default (add `delete_project` call if needed)
- Uses the same deterministic naming convention — no manual resource names required
- Idempotent and safe to re-run

## Pre-Flight Validation (Stage V)

Before provisioning, the script runs comprehensive pre-flight checks:

- gcloud version (>= 450.0.0)
- Required tools: `docker`, `jq`, `openssl`, `sha256sum`
- Docker daemon accessibility
- gcloud authentication + Application Default Credentials
- Network connectivity to Google APIs
- Billing account availability
- Organization policy awareness
- Region availability
- Project quota limits
- Prerequisite APIs (Cloud Resource Manager, Service Usage, IAM, Cloud Billing)

Run validation independently:
```bash
./start.sh dev --dry-run --no-welcome  # Runs validation in dry-run mode
```

## What it does (stages)

| Stage | Name                  | Description                                         |
|-------|-----------------------|-----------------------------------------------------|
| V     | **Pre-Flight Validation** | **NEW**: Validates gcloud, tools, auth, billing, quotas, region, APIs before any resource creation |
| 0     | **Generate Names**    | **NEW**: Generates and displays ALL resource names for approval (single prompt) |
| 1     | Create Project        | Creates GCP project with auto-generated name       |
| 2     | Enable APIs           | Enables required GCP APIs (Secret Manager, Compute, Firestore, Cloud Run, Pub/Sub, Eventarc, etc.) — waits until all APIs are fully enabled before continuing |
| 3     | Config & Project Info | Creates a gcloud configuration, stores project number |
| 4     | Create Main Bucket    | Creates the primary GCS bucket for the project     |
| 4b    | Create Public Buckets | Creates public input/output buckets for user uploads |
| 4c    | Create Build Bucket   | Creates Cloud Build staging bucket                 |
| 5     | Create Service Accounts | Creates Dropbox, Strava, Run, and Eventarc service accounts |
| 5b    | Create Deployer SA     | Creates the CI/CD deployer SA (`bike-ci-deployer`) and binds `run.admin`, `artifactregistry.writer`, `storage.objectViewer`, `logging.logWriter`, `serviceAccountUser` on the Run SA, `objectAdmin`+`admin` on the build bucket, plus `serviceAccountUser` for `MY_USER_ACCOUNT` (needed by `power_core_run.sh` / `site_handler_run.sh`) |
| 6     | Create Secrets        | Creates secrets in Secret Manager: a **combined Dropbox+Strava secret** and a **fullstack JSON keys secret** (with placeholder values) |
| 7     | Bind IAM Roles        | Assigns roles to SAs, compute engine, and user account; grants impersonation roles; verifies secret access bindings |
| 8     | Pub/Sub Setup         | Creates public topic (`GCP_TOPIC_NAME`) and private topic (`DROPBOX_TOPIC_NAME`) + their dead-letter topics, the Eventarc SA, grants `eventarc.eventReceiver` + `iam.serviceAccountTokenCreator` to the Pub/Sub agent, and creates the **private push subscription** (placeholder URL). The Eventarc trigger + real push URL are wired after first deploy via `./wire_pubsub.sh` |
| 9     | Artifact Registry     | Creates a Docker repository and configures Docker auth |
| 11    | JSON Credentials      | **Optional** — downloads a key file for the Run SA only if `GOOGLE_APPLICATION_CREDENTIALS` is set |
| 12    | Create Firestore      | Creates a Firestore database in the specified region |

> Stage 10 is omitted intentionally — numbering matches the original deployment plan.
> Stage 6 (secrets) intentionally runs **before** Stage 7 (IAM binding + verification), because the access verification in Stage 7 reads the secrets and binding roles requires the secrets to already exist. If you have an old `script_progress.log`, remove it (or re-run with `reset`) so the renumbered stages take effect.

## Post-deploy Pub/Sub wiring (`wire_pubsub.sh`)

The push subscription and the Eventarc trigger both need the **Cloud Run service URL**, which only
exists **after the first deploy** (`power_core_run.sh`). The bootstrap therefore creates:

- the public topic + DLQ and the **private** push subscription with a **placeholder URL**
  (`https://placeholder.invalid/private-processing-handler`),
- the Eventarc SA and its IAM grants,
- but **not** the `run.invoker` binding or the Eventarc trigger.

Once the first deploy succeeds, run:

```bash
./wire_pubsub.sh dev     # or prod
```

This auto-detects the Cloud Run URL and:
1. Points the private push subscription at `{URL}/private-processing-handler`
2. Grants `roles/run.invoker` to the Eventarc SA on the Cloud Run service
3. Creates the Eventarc trigger `{org}-{env}-{app}-pubsub-trigger` → `{URL}/pubsub-processing-handler`

It then reminds you to set `EVENTARC_SA` and `EVENTARC_TRIGGER` inside the
`fullstack-app-json-keys` secret. Override the detected URL with `CLOUD_RUN_URL=https://...`.

## Naming Convention (NEW)

All resource names now follow **Google Cloud best practices**: `{org}-{env}-{app}-{component}`

### Examples

| Resource | Pattern | Example (dev) | Example (prod) |
|----------|---------|---------------|----------------|
| Project | `{org}-{env}-{app}` | `bigbikedata-dev-power-core` | `bigbikedata-prod-power-core` |
| Main Bucket | `{org}-{env}-{app}-main-{hash}` | `bigbikedata-dev-power-core-main-a1b2c3` | `bigbikedata-prod-power-core-main-x9y8z7` |
| Public Output Bucket | `{org}-{env}-{app}-output-{hash}` | `bigbikedata-dev-power-core-output-a1b2c3` | `bigbikedata-prod-power-core-output-x9y8z7` |
| Public Input Bucket | `{org}-{env}-{app}-input-{hash}` | `bigbikedata-dev-power-core-input-a1b2c3` | `bigbikedata-prod-power-core-input-x9y8z7` |
| Build Bucket | `{org}-{env}-{app}-build-{hash}` | `bigbikedata-dev-power-core-build-a1b2c3` | `bigbikedata-prod-power-core-build-x9y8z7` |
| Service Accounts | `{org}-{env}-{purpose}` | `bigbikedata-dev-dropbox` | `bigbikedata-prod-dropbox` |
| Deployer SA | `bike-ci-deployer` | `bike-ci-deployer` | `bike-ci-deployer` |
| Secrets (Dropbox+Strava) | `{org}-{env}-{app}-dropbox-secrets` | `bigbikedata-dev-power-core-dropbox-secrets` | `bigbikedata-prod-power-core-dropbox-secrets` |
| Secrets (JSON Keys)      | `{org}-{env}-{app}-fullstack-app-json-keys` | `bigbikedata-dev-power-core-fullstack-app-json-keys` | `bigbikedata-prod-power-core-fullstack-app-json-keys` |
| Artifact Registry | `{org}-{env}-{app}-docker` | `bigbikedata-dev-power-core-docker` | `bigbikedata-prod-power-core-docker` |
| Public Pub/Sub Topic | `{org}-{env}-{app}-topic` | `bigbikedata-dev-power-core-topic` | `bigbikedata-prod-power-core-topic` |
| Private Pub/Sub Topic | `{org}-{env}-{app}-dropbox-topic` | `bigbikedata-dev-power-core-dropbox-topic` | `bigbikedata-prod-power-core-dropbox-topic` |
| Private Pub/Sub Subscription | `{org}-{env}-{app}-dropbox-sub` | `bigbikedata-dev-power-core-dropbox-sub` | `bigbikedata-prod-power-core-dropbox-sub` |
| Eventarc Trigger | `{org}-{env}-{app}-pubsub-trigger` | `bigbikedata-dev-power-core-pubsub-trigger` | `bigbikedata-prod-power-core-pubsub-trigger` |
| Cloud Run Services | `{org}-{env}-{app}-{service}` | `bigbikedata-dev-power-core-core` | `bigbikedata-prod-power-core-core` |

**Bucket uniqueness**: Storage buckets require globally unique names. A 6-character hash suffix (SHA256 of `{org}-{env}-{app}`) is appended to all bucket names.

**Service account length**: GCP limits service account IDs to **6–30 characters**, so the full
`{org}-{env}-{app}-{purpose}` pattern would overflow (e.g. `bigbikedata-dev-power-core-dropbox` is 34 chars).
Service accounts therefore use `{org}-{env}-{purpose}`. Since each project already encodes
`{org}-{env}-{app}` and service accounts are scoped per project, no collisions can occur.

### Stage 0: Single Approval Workflow

1. Script reads `ORG_PREFIX` and `APP_NAME` from `keys.env.{env}` (or prompts once if missing)
2. Generates **ALL** resource names upfront using the naming convention
3. Displays a formatted table of every resource name
4. Single prompt: **Y** = approve all, **N** = re-enter org prefix
5. On approval, all stages use pre-generated names — no more per-stage prompts

## Environment-Specific Behavior

The `ENV_MODE` (`prod` or `dev`) is embedded in every resource name at position 2. There is **no suffix appending** — the environment is part of the canonical name.

### Production (`prod`)
- Reads `ORG_PREFIX=bigbikedata`, `APP_NAME=power-core` from `keys.env.prod`
- Generates names like `bigbikedata-prod-power-core-*`

### Development (`dev`)
- Reads `ORG_PREFIX=bigbikedata`, `APP_NAME=power-core` from `keys.env.dev`
- Generates names like `bigbikedata-dev-power-core-*`
- Uses placeholder/test values for secrets (not production tokens)

## Progress tracking

The script writes a `script_progress_{env}.log` file to track completed stages per environment. If the script is interrupted, re-running it skips already-finished stages. Pass `reset` to clear the log and re-run everything.

Generated resource names are deterministic (derived from `ORG_PREFIX` + `APP_NAME` + `ENV_MODE`), so on a
resumed run the name variables are regenerated automatically even though the approval stage is skipped.
Previously recorded values from `names.env` (e.g. `GCP_PROJECT_NUMBER`) are also re-loaded at startup, so
later stages that need them (IAM, Pub/Sub) work correctly even when the stage that recorded them was skipped.

## Output

A `names.env` file is generated containing:
- `GCP_PROJECT_ID` — the new project ID
- `GCP_PROJECT_NUMBER` — the numeric project number
- `GCP_BUCKET_NAME` — the created bucket name
- All other auto-generated resource names

Entries are appended only once per key, so re-runs do not duplicate them.

## Security notes

- **`keys.env.{prod|dev}` holds sensitive credentials in plaintext.** It contains your user
  email and the secrets used to provision the Dropbox/Strava API tokens. It is recommended to
  protect it at rest (e.g., store an encrypted copy with `gpg`/`sops` and decrypt into a
  temporary file only when running) and to never commit it to version control.
- **Secrets are created with placeholder values.** Stage 6 stores placeholder data as the first secret versions so the project bootstraps end-to-end. After setup, replace them with the real tokens via `gcloud secrets versions add`:
  - **Combined secret** (`{org}-{env}-{app}-dropbox-secrets`): Add Dropbox (App Key, App Secret, Refresh Token) and Strava (Client ID, Client Secret, Refresh Token) credentials
  - **JSON keys secret** (`{org}-{env}-{app}-fullstack-app-json-keys`): Add service account JSON keys and other JSON credentials
  This also means the access-binding verification in Stage 7 only proves *IAM access*, not the correctness of the token data.
- **Development environment**: Use test/placeholder tokens only. Never use production API credentials in the dev project.

## Combined secret reference (`{org}-{env}-{app}-fullstack-app-json-keys`)

After the bootstrap completes, the **JSON keys secret** still holds placeholder data. It must be
re-filled with the app's runtime configuration before the services work end-to-end. The payload is a
**flat JSON object**: each key is the name of an environment variable, each value its content. At
startup, `InjectConfig` (in `gcp_actions`) fetches this secret and injects every key into the
process environment, so the names below must match exactly what `config.py` and
`site_config.py` read.

This table is the authoritative key reference — it is mirrored by the Secret Manager emulator seeder
(`gcp_actions/gcp_actions/emulators/secret_manager/seed.py`, `SECRET_CONFIG_MAP`) and by the full
[`config-manifest.md`](config-manifest.md) (adds storage layer, consumers, anti-drift checklist).

### How to re-fill the secret

```bash
# Build the JSON (example for dev — values below explain each field)
gcloud secrets versions add bigbikedata-dev-power-core-fullstack-app-json-keys \
    --data-file=payload.json \
    --project=bigbikedata-dev-power-core
```

The example values in the table are generated deterministically by the bootstrap naming convention
(`lib/naming_convention.sh`) and already present in `keys.env.{env}` / `names.env` — copy them from
there instead of retyping.

### Key reference

| Key | Meaning — what the app does with it | Where the value comes from | Still needed? |
|-----|--------------------------------------|----------------------------|---------------|
| `GCP_PROJECT_ID` | Project ID; required to reach Secret Manager/Firestore/GCS | `keys.env.{env}` / `names.env` (`GCP_PROJECT_ID`) | **Yes** — hard-required pre-flight |
| `APP_JSON_KEYS` | Name of **this** secret (pointer). Set via Cloud Run env, *not* stored inside the payload | `keys.env.{env}` (`APP_JSON_KEYS`) | **Yes** — but as env var, skip the key |
| `SEC_DROPBOX` | Name of the combined Dropbox+Strava secret (accessor) | `keys.env.{env}` (`SEC_DROPBOX`) | **Yes** — hard-required pre-flight |
| `S_ACCOUNT_RUN` | Cloud Run service-account email; used for signed-URL impersonation | `bigbikedata-{env}-run@…iam.gserviceaccount.com` (see `S_ACCOUNT_RUN` in `keys.env.{env}`) | **Yes** — signed URLs + pre-flight |
| `S_ACCOUNT_DROPBOX` | Dropbox SA email; used to read `SEC_DROPBOX` | `bigbikedata-{env}-dropbox@…iam.gserviceaccount.com` | **Yes** — hard-required pre-flight |
| `GCS_BUCKET_NAME` | Main GCS bucket for downloads | `names.env` `GCP_BUCKET_NAME` | **Yes** — workers + uploads |
| `GCS_PUB_OUTPUT_BUCKET` | Public output bucket | `names.env` `GCS_PUB_OUTPUT_BUCKET` | **Yes** — workers |
| `GCP_TOPIC_NAME` | Public pipeline Pub/Sub topic (frontend uploads) | `keys.env.{env}` (`GCP_TOPIC_NAME`) | **Yes** — site_handler publishes |
| `DROPBOX_TOPIC_NAME` | Private pipeline Pub/Sub topic (Dropbox sync) | `keys.env.{env}` (`DROPBOX_TOPIC_NAME`) | **Yes** — `get_from_dropbox` |
| `CLOUD_RUN_SERVICE` | Core Cloud Run service name | `keys.env.{env}` (`CLOUD_RUN_SERVICE`) | Optional — read into config only |
| `CLOUD_RUN_SERVICE_PUB` | Site-handler Cloud Run service name | `keys.env.{env}` (`CLOUD_RUN_SERVICE_PUB`) | Optional — read into config only |
| `EVENTARC_SA` | Eventarc SA email | `{org}-{env}-eventarc@…iam.gserviceaccount.com` + `wire_pubsub.sh` | Optional — stored for reference |
| `EVENTARC_TRIGGER` | Eventarc trigger name | `{base}-pubsub-trigger` + `wire_pubsub.sh` | Optional — stored for reference |
| `EMAIL_MODE` | `brevo` or `local` (SMTP switch) | Choose; dev uses `brevo` | **Yes** — email backend |
| `BREVO_API_KEY` | Brevo (Sendinblue) API key | Brevo dashboard → **SMTP & API → API keys** | **Yes** (if `EMAIL_MODE=brevo`) |
| `SENDER_EMAIL` | "From" address for Brevo | Brevo verified sender (dev: `develop@offteleport.cloud`) | **Yes** (brevo) |
| `SENDER_NAME` | Display name for Brevo sender | Your choice | **Yes** (brevo) |
| `SMTP_SERVER` | SMTP host (e.g. `smtp.gmail.com`) | Only if using SMTP path | Only if `EMAIL_MODE≠brevo` |
| `SMTP_PORT` | SMTP port (`587` / `465`) | Same | Only if `EMAIL_MODE≠brevo` |
| `SMTP_SENDER` | SMTP "From" address | Same | Only if `EMAIL_MODE≠brevo` |
| `SMTP_USER` | SMTP login | Same | Only if `EMAIL_MODE≠brevo` |
| `SMTP_PASSWORD` | SMTP password | Same | Only if `EMAIL_MODE≠brevo` |
| `PRIVATE_UPLOAD_TOKEN` | Secret path segment for the private upload endpoint | `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` | **Yes** — route in `transfer.py` |
| `DROpbox_WEBHOOK_PATH` | Path of the Dropbox webhook endpoint (note odd casing — keep it) | Random path; rotate with `./local_dev.sh cmd_rotate_webhook` | **Yes** — route in `transfer.py` |
| `FLASK_SECRET_KEY` | Flask session signing key (site_handler) | `python3 -c "import secrets; print(secrets.token_hex(32))"` | **Yes** — hard-fails if missing in cloud |
| `FRONTEND_BASE_URL` | Public site URL used for download links | e.g. `https://bigbikedata--dev-app.web.app` / `https://bigbikedata.web.app` | **Yes** — `instruments.py` |
| `DONATION_HTML_SNIPPET_MONO` | Donation-block HTML from Monobank jar | Monobank jar donate widget generator | **Yes** — rendered donation section |
| `DONATION_HTML_SNIPPET_PRIVAT` | Donation-block HTML from Privat24 jar | Privat24 jar widget generator | **Yes** — rendered donation section |
| `STRAVA_UPLOAD` | Strava upload toggle: `enable` / `disable` | Feature flag; **dev = `disable`** (Strava is now paid for API actions) | **Yes** — toggles upload stage |
| `PRIVATE_ACCESS_TOKEN` | Historic private-upload token | Legacy from old project | **No** — defined in `config.py` but untouched by runtime code |
| `COOKIE_DOMAIN` | Cookie domain | Legacy | **No** — read into config only, no consumer |
| `SEC_STRAVA` | Strava secret pointer | Legacy; production path uses `SEC_DROPBOX` | **No** — only a local dev helper (`strava/local`) |
| `S_ACCOUNT_STRAVA` | Strava SA email | Legacy | **No** — only `strava/local` |
| `BACKEND_TAG` | Backend image tag | Build-time only (`deploy_utils.sh`) | **No** — not a runtime secret |
| `FRONTEND_TAG` | Frontend image tag | Build-time only | **No** — not a runtime secret |

> **Legacy naming:** the original project used lowercase `s_email_run`/`s_email_dropbox`
> keys; current code and the emulator seeder use `S_ACCOUNT_RUN`/`S_ACCOUNT_DROPBOX`. Use the
> uppercase names. `site_config.py` in `site_handler` still probes `s_email_run`, but the value is
> supplied by the `S_ACCOUNT_RUN` Cloud Run env var.

### Config that lives in Firestore (non-secret variables)

`InjectConfig` merges three layers (Firestore → local config → Secret Manager, secret wins). Every
non-secret runtime variable should be stored in the Firestore document
`config/local/settings/data` (`FirestoreMagic("config", "local/settings/data")`) — **not** in the
secret — because it is read on **every container start**:

- **Cost**: each Secret Manager access costs money per API call; Firestore reads are far cheaper.
  Storing frequently-read non-secret values in the secret would multiply Secret Manager billing
  across every instance start, so only genuinely sensitive values (API keys, tokens, passwords) go
  into Secret Manager, while the cheap-to-read configuration stays in Firestore.
- **Runtime access**: the service fetches these variables at boot; pulling them from Firestore (and
  letting the secret override only what it must) keeps the hot path cheap and non-blocking.

A freshly bootstrapped project creates that document **empty**, so those values silently disappear —
this is why you see keys "missing" after deploy even though the secret lists them.

> **Do NOT re-seed from the original `voltaic-bridge-477610-h2` project.** Its Firestore doc holds
> that project's **dev resource values** (bucket names, topic names, etc.), which do not exist in
> the new project. Populate the new Firestore doc with **this** project's values instead (they are
> recorded in `keys.env.{env}` / `names.env`).

Seed the new project's Firestore config doc manually (values must match the current project):

1. Create the document with the `{env}`-correct values, for example:

   ```json
   {
     "CS_BUCKET_NAME": "bigbikedata-dev-power-core-main-3eea25",
     "EMAIL_MODE": "brevo",
     "GCS_PUB_INPUT_BUCKET": "bigbikedata-dev-power-core-input-3eea25",
     "GCS_PUB_OUTPUT_BUCKET": "bigbikedata-dev-power-core-output-3eea25",
     "DROPBOX_TOPIC_NAME": "bigbikedata-dev-power-core-dropbox-topic",
     "LOGGING_LEVEL": "INFO"
   }
   ```

2. Upload it (or reuse the helper):

   ```bash
   FIRESTORE_EMULATOR_HOST= gcloud firestore documents set \
       "config/local/settings/data" --data=firestore_config.json
   # or use the seeder with an explicit defaults file for the new project:
   #   python gcp_actions/gcp_actions/emulators/firestore/seed.py --defaults-file firestore_config.json
   ```

Default keys that routinely live in the Firestore doc (`seed.py` `DEFAULT_CONFIG`):
`CS_BUCKET_NAME`, `EMAIL_MODE`, `GCS_PUB_INPUT_BUCKET`, `GCS_PUB_OUTPUT_BUCKET`,
`DROPBOX_TOPIC_NAME`, `LOGGING_LEVEL`. Never move these into the secret — keep them in Firestore for
cost reasons.

## Extending

- Place reusable functions in `lib/*.sh`
- Place addon modules in `addons/*.sh`
- Deprecated modules are in `lib/deprecated/`

## Migration from Old Naming

The old naming generator (`lib/deprecated/naming_generator.sh`) used manual prompts per resource with random suffixes. The new convention (`lib/naming_convention.sh`) is deterministic, readable, and follows industry standards. Existing projects are unaffected — this only applies to new project creation.