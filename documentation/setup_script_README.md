# GCP Project Bootstrap Script

This script automates provisioning a new GCP project for the **BigBikeData / power_core** application. It handles project creation, IAM, secrets, Pub/Sub, Artifact Registry, Cloud Run, and Firestore setup.

Supports **dual-environment provisioning**: `prod` (production) and `dev` (development).

> This bootstrap provisions real GCP infrastructure. It is not required for the
> basic local emulator startup in `power_core/README.md`. Local development is
> hybrid: Secret Manager, Firestore, and Pub/Sub can run in local emulators,
> while Cloud Storage and external APIs remain real services when those pipeline
> stages are exercised. Use this bootstrap when you need the dev/prod GCP layer
> or Cloud Run deployment.

## One-shot full setup (`main.sh`)

**`main.sh` is the new top-level entry point** that replaces the old bare
`start.sh` workflow. It guides you through the whole environment setup in three
phases and never leaves you with a silent "everything is ready":

1. **Phase 1 — External Services wizard (interactive).** A guided walkthrough
   of [`external_services_setup.md`](external_services_setup.md): Dropbox,
   Strava, Brevo/SMTP, site hosting, and ngrok. Values are collected
   interactively and saved **encrypted (gpg)** to
   `.external_services.{env}.gpg` — never in plaintext. It ends with a summary
   table showing every configured variable and where it will be stored.
2. **Phase 2 — Cloud bootstrap.** Delegates to `./start.sh {env}`.
3. **Phase 3 — Runtime config.** Runs `./configure_runtime.sh {env} --apply`
   (Firestore + generated `fullstack-app-json-keys` values) and uploads the
   wizard-collected external credentials into the `dropbox-secrets` and
   `fullstack-app-json-keys` Secret Manager secrets.

```bash
# Full guided setup (recommended for new environments)
./main.sh dev
./main.sh prod

# Unattended / CI preview (skip wizard, no GCP changes)
./main.sh dev --dry-run --no-wizard

# Auto-approve the wizard confirmation prompt
./main.sh dev --yes
```

Re-running `main.sh` prefills every previously-entered value from the encrypted
state file — only the Diff-vs-last-run questions are asked again.

> gpg is required for the encrypted state file. On re-run you are asked for the
> passphrase; keep it safe (it protects the collected provider tokens at rest).

## Quick Start (Interactive Welcome Phase)

**New users**: Just run the script! It will guide you through all required configuration interactively:

```bash
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
- **Firebase CLI** (`firebase`) installed — `npm i -g firebase-tools` (used by
  Stage 13 to link Firebase Hosting to the bootstrapped project)
- **Docker** installed (for Artifact Registry authentication)
- **`python3`** and **`jq`** on `PATH` (used by preprocessing helpers)

> The scripts **do not require an activated virtual environment**. They locate
> the environment file by scanning, in order: `$VIRTUAL_ENV/../keys.env.{env}`
> (if a venv is active), then `dirname($VIRTUAL_ENV)/keys.env.{env}`, then
> `documentation/startup/../../power_core/keys.env.{env}` (this project).

### Environment file (`keys.env.{prod|dev}`)

The script looks for `keys.env.{prod|dev}` in several locations (see
[Prerequisites](#prerequisites)) and uses the first one found — for this project
that resolves to `power_core/keys.env.{env}`. If the file doesn't exist, the
Welcome Phase creates/collects it for you. To prefill values, copy the templates
(`keys.env.prod.template` / `keys.env.dev.template` at the repo root) there.

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

### External service credentials (required before cloud setup)

Dropbox, Strava, email (Brevo/SMTP), and site-hosting credentials are
**per-environment, manually-obtained values** that must be prepared **before**
provisioning the cloud project. Full setup instructions, per-service variables,
and the pre-flight checklist are in
**[`external_services_setup.md`](external_services_setup.md)**.

In short: create a **separate Dropbox app/account per environment**, one shared
Strava app (with a per-env upload toggle), one Brevo account with a separate
sender per env, and a Firebase Hosting site with a custom domain. These
credentials are stored in the **combined `dropbox-secrets` secret** and the
**`fullstack-app-json-keys` secret** — never in `keys.env`.

## Usage

```bash
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
| 13    | Firebase Hosting link | Links the site_handler hosting project to the bootstrapped GCP project (`firebase` CLI or `site_handler/.firebaserc`); reports what stays manual (custom domain + DNS) |

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

## Runtime Configuration After Bootstrap

`start.sh` provisions infrastructure and creates the two application secrets
with placeholder values. It does not obtain credentials from Dropbox, Strava,
Brevo, SMTP, Wahoo, or ngrok — those external credentials are prepared
separately (see [`external_services_setup.md`](external_services_setup.md)) and
stored into the secrets after bootstrap.

The naming stage generates more values than are needed during resource
creation. They are persisted in `names.env`, including project and bucket
names, service account names and emails, Secret Manager names, Pub/Sub
resources, Artifact Registry, Cloud Run services, and Eventarc resources.

After bootstrap, prepare the runtime layers with:

```bash
./configure_runtime.sh dev --dry-run
./configure_runtime.sh dev --apply
```

Use `prod` instead of `dev` for production. The script is safe to re-run. By
default it performs no cloud writes. With `--apply` it writes generated
non-secret values to `config/local/settings/data` in Firestore and creates a
new version of the generated `fullstack-app-json-keys` secret containing the
generated application values.

The `--apply` command refuses to write an incomplete application payload. Set
the reported hard-required values, such as `FRONTEND_BASE_URL`, in the
environment file before applying it.

The following application-owned values are generated automatically when they
do not already exist:

- `FLASK_SECRET_KEY` — Flask session signing key;
- `PRIVATE_UPLOAD_TOKEN` — token for the private upload endpoint;
- `DROpbox_WEBHOOK_PATH` — secret path used by the Dropbox webhook.

They are included in the `fullstack-app-json-keys` payload. Re-running the
helper with `--apply` preserves existing values from Secret Manager, so it does
not rotate these values accidentally.

It does not update `dropbox-secrets` until external Dropbox and Strava values
are supplied. Use the [configuration manifest](config-manifest.md) to build
that payload and verify the required keys for the selected environment.

The generated values are resource names, not credentials. `names.env` must not
be treated as a replacement for Secret Manager.

## Naming Convention

All resource names follow **Google Cloud best practices**: `{org}-{env}-{app}-{component}`,
with the environment (`prod`/`dev`) embedded at position 2 (no suffix appending).
The full resource→pattern→example table lives in **`config-manifest.md` §3** — it is
not duplicated here.

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

## Config reference (single source)

The bootstrap needs very few variables from you (see [What you actually need to
provide](#what-you-actually-need-to-provide)). For everything else — the full
variable registry, the JSON-keys / dropbox-secrets payload composition, how to
re-fill the secrets, the Firestore layer, and the anti-drift verifier — see
**[`config-manifest.md`](config-manifest.md)**. That file is the single source
of truth; this README does not duplicate its tables.

## Extending

- Place reusable functions in `lib/*.sh`
- Place addon modules in `addons/*.sh`
- Deprecated modules are in `lib/deprecated/`

## Migration from Old Naming

The old naming generator (`lib/deprecated/naming_generator.sh`) used manual prompts per resource with random suffixes. The new convention (`lib/naming_convention.sh`) is deterministic, readable, and follows industry standards. Existing projects are unaffected — this only applies to new project creation.
