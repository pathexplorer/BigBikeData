# Config Manifest — BigBikeData / power_core

Single source of truth for **every** environment variable the project uses, and
exactly where each value lives. Use this table when you need to re-create an
environment (prod/dev), add a new variable, or debug "why is my value missing".

> This manifest is the **authoritative** combined reference. The bootstrap
> README (`README.md`) and the emulator seeder
> (`gcp_actions/.../emulators/secret_manager/seed.py` → `SECRET_CONFIG_MAP`)
> are mirrors of the same data.
>
> If you change an env var here, update all three in lockstep, then re-run the
> verifier described below.

---

## 1. Where configuration lives (4 layers)

| # | Layer | Storage | Loaded at | Cost | Notes |
|---|-------|---------|-----------|------|-------|
| 1 | **Bootstrap input** | `keys.env.{dev/prod}` (next to virtualenv, gitignored) | `./start.sh` welcome/stage 0 | – | Only genuine user input + deterministic naming inputs |
| 2 | **Bootstrap output** | `names.env` (in `docs/scripts/startup/`) | `./start.sh` on resume | – | Every generated resource name, persisted once |
| 3 | **Secret Manager** | `fullstack-app-json-keys` + `dropbox-secrets` secrets | Cloud Run boot (`InjectConfig`) | 💰 paid per API call | Only sensitive values go here |
| 4 | **Firestore** | document `config/local/settings/data` | every container start (`InjectConfig`) | cheap | Non-secret, frequently-read config |

**Merge order (`InjectConfig`):** Firestore → local config → Secret Manager
**(secret wins).**

---

## 2. Full variable registry

Status flags:
- **Hard** — required; app fails to boot without it.
- **Opt** — read only if feature/toggle enabled.
- **Ref** — read into config, no active consumer (legacy/reference only).
- **EnV** — set as Cloud Run *env var* on the service, *not* stored in the secret.

| Variable | Layer | Where | Required in prod | Required in dev | Consumers |
|----------|-------|-------|:---:|:---:|-----------|
| `MY_USER_ACCOUNT` | 1 | `keys.env.{env}` | Hard | Hard | Bootstrap IAM bindings (Stage 7) |
| `REGION` | 1 | `keys.env.{env}` | Hard | Hard | Bootstrap (buckets, Firestore) |
| `GCONFIG_NAME` | 1 | `keys.env.{env}` | Hard | Hard | Bootstrap gcloud config (Stage 3) |
| `ORG_PREFIX` | 1 | `keys.env.{env}` | Hard | Hard | Naming convention Stage 0 |
| `APP_NAME` | 1 | `keys.env.{env}` | Hard | Hard | Naming convention Stage 0 |
| `SA_DEPLOYER_EMAIL` | 1 | `keys.env.{env}` | Hard | Hard | Bootstrap Stage 5b |
| `GCP_PROJECT_ID` | 1/2/3 | `keys.env.{env}` + `names.env` + secret + Cloud Run EnV | Hard | Hard | `config.py`, `site_config.py`, pre-flight |
| `GCP_PROJECT_NUMBER` | 2 | `names.env` | Hard | Hard | Bootstrap IAM/resource links |
| `S_ACCOUNT_RUN` | 1/2/3 | `keys.env.{env}` + secret | Hard | Hard | `config.py` (signed URLs, pre-flight), `site_config.py` (as `s_email_run`) |
| `S_ACCOUNT_DROPBOX` | 1/2/3 | `keys.env.{env}` + secret | Hard | Hard | `config.py` (pre-flight), reads `SEC_DROPBOX` |
| `S_ACCOUNT_STRAVA` | 1/3 | generated + secret | Ref | Ref | `strava/local` only |
| `SEC_DROPBOX` | 1/3/EnV | `keys.env.{env}` + pointer | Hard | Hard | `config.py` (pre-flight), `get_from_dropbox` |
| `APP_JSON_KEYS` | 1/EnV | `keys.env.{env}` + Cloud Run EnV | Hard | Hard | `config.py`, `site_config.py` (points to own secret) |
| `SEC_STRAVA` | 3 | secret | Ref | Ref | `strava/local` only |
| `ARTIFACT_REGISTRY` | 1/2 | `keys.env.{env}` + `names.env` | Bootstrap | Bootstrap | Deploy / Docker auth |
| `GCP_TOPIC_NAME` | 1/3 | `keys.env.{env}` + secret | Hard | Hard | `config.py`, `site_config.py` (site_handler publishes) |
| `DROPBOX_TOPIC_NAME` | 1/3/4 | keys.env + secret + Firestore | Hard | Hard | `config.py` (`get_from_dropbox`) |
| `DROPBOX_SUBSCRIPTION_NAME` | 1/2 | `keys.env.{env}` + `names.env` | Bootstrap | Bootstrap | Pub/Sub setup |
| `GCP_DLQ_TOPIC_NAME` | 2 | generated | Bootstrap | Bootstrap | Pub/Sub DLQ |
| `DROPBOX_DLQ_TOPIC_NAME` | 2 | generated | Bootstrap | Bootstrap | Pub/Sub DLQ |
| `CLOUD_RUN_SERVICE` | 1/3 | `keys.env.{env}` + secret | Opt | Opt | `config.py`, `site_config.py` |
| `CLOUD_RUN_SERVICE_PUB` | 1/3 | `keys.env.{env}` + secret | Opt | Opt | `config.py` |
| `EVENTARC_SA` | 3 | secret (post-`wire_pubsub.sh`) | Ref | Ref | Config only; wire/wiring scripts |
| `EVENTARC_TRIGGER` | 3 | secret (post-`wire_pubsub.sh`) | Ref | Ref | Config only |
| `GCS_BUCKET_NAME` | 1/3/4 | keys.env + secret + Firestore | Hard | Hard | `config.py` (workers), `site_config.py` |
| `GCS_PUB_OUTPUT_BUCKET` | 1/3/4 | keys.env + secret + Firestore | Hard | Hard | `config.py` (workers) |
| `GCS_PUB_INPUT_BUCKET` | 4 | Firestore only | Hard | Hard | `config.py` (uploads) |
| `GCS_BUILD_BUCKET` | 1/2 | `keys.env.{env}` + `names.env` | Bootstrap | Bootstrap | Cloud Build staging |
| `CS_BUCKET_NAME` | 4 | Firestore only | Hard | Hard | `config.py` (download link bucket) |
| `ALLOWED_DOMAINS` | EnV | Cloud Run env (site_handler) | Hard | Hard | `site_config.py` security middleware |
| `EMAIL_MODE` | 3/4 | secret + Firestore | Opt (`brevo`/`local`) | Opt | `config.py` email backend switch |
| `BREVO_API_KEY` | 3 | secret | Opt (if brevo) | Opt (if brevo) | `config.py` |
| `SENDER_EMAIL` | 3 | secret | Opt (if brevo) | Opt (if brevo) | `config.py` |
| `SENDER_NAME` | 3 | secret | Opt (if brevo) | Opt (if brevo) | `config.py` |
| `SMTP_SERVER` | 3 | secret | Opt (`EMAIL_MODE≠brevo`) | Opt | `config.py` |
| `SMTP_PORT` | 3 | secret | Opt | Opt | `config.py` |
| `SMTP_SENDER` | 3 | secret | Opt | Opt | `config.py` |
| `SMTP_USER` | 3 | secret | Opt | Opt | `config.py` |
| `SMTP_PASSWORD` | 3 | secret | Opt | Opt | `config.py` |
| `PRIVATE_UPLOAD_TOKEN` | 3 | secret | **Hard** | **Hard** | `transfer.py` private upload route |
| `DROpbox_WEBHOOK_PATH` | 3 | secret (note odd casing!) | **Hard** | **Hard** | `transfer.py` webhook route |
| `FLASK_SECRET_KEY` | 3 | secret | Hard | Hard | `site_config.py` session signing |
| `FRONTEND_BASE_URL` | 3 | secret | Hard | Hard | `instruments.py` download links |
| `DONATION_HTML_SNIPPET_MONO` | 3 | secret | Opt | Opt | donation section render |
| `DONATION_HTML_SNIPPET_PRIVAT` | 3 | secret | Opt | Opt | donation section render |
| `STRAVA_UPLOAD` | 3 | secret | Opt (`enable`/`disable`) | **Hard `disable`** | toggles Strava upload stage |
| `PRIVATE_ACCESS_TOKEN` | 3 | secret | Ref | Ref | `config.py` only, no consumer |
| `COOKIE_DOMAIN` | 3 | secret | Ref | Ref | `config.py` only, no consumer |
| `BACKEND_TAG` | 3 | secret | Ref | Ref | build-time only (`deploy_utils.sh`) |
| `FRONTEND_TAG` | 3 | secret | Ref | Ref | build-time only |
| `LOGGING_LEVEL` | 4 | Firestore | Opt | Opt | logging config (note: hardcoded `DEBUG` in `config.py:90`) |
| `DROPBOX_WATCHED_FOLDER` | EnV | optional Cloud Run env | Opt | Opt | `config.py` (default `/apps/activities`) |

### Combined Dropbox+Strava secret payload (`SEC_DROPBOX` → `{org}-{env}-{app}-dropbox-secrets`)

| Variable | Required | Notes |
|----------|:---:|-------|
| `DROPBOX_APP_KEY` | Hard | Dropbox dev console → app key |
| `DROPBOX_APP_SECRET` | Hard | Dropbox dev console → app secret |
| `DROPBOX_REFRESH_TOKEN` | Hard | OAuth2 refresh token |
| `STRAVA_CLIENT_ID` | Opt | Strava API |
| `STRAVA_CLIENT_SECRET` | Opt | Strava API |
| `STRAVA_REFRESH_TOKEN` | Opt | Strava OAuth refresh |
| `STRAVA_ACCESS_TOKEN` | Ref | emulator/legacy |
| `STRAVA_EXPIRES_AT` | Ref | emulator/legacy |

> The emulator seeder also lists `STRAVA_APP_ID` — this name is **superseded**
> by `STRAVA_CLIENT_ID`. Only the modern names are used by the app.

---

## 3. Deterministic naming reference (derive, don't memorize)

Everything below the first 6 rows is **derived**, not configured. Never type
these names by hand — copy from `keys.env.{env}` / `names.env` or re-run the
naming convention.

| Resource | Pattern | dev example | prod example |
|----------|---------|-------------|--------------|
| Project | `{org}-{env}-{app}` | `bigbikedata-dev-power-core` | `bigbikedata-prod-power-core` |
| Main Bucket | `{base}-main-{hash}` | `bigbikedata-dev-power-core-main-3eea25` | `bigbikedata-prod-power-core-main-9e8f54` |
| Output Bucket | `{base}-output-{hash}` | `...-output-3eea25` | `...-output-9e8f54` |
| Input Bucket | `{base}-input-{hash}` | `...-input-3eea25` | `...-input-9e8f54` |
| Build Bucket | `{base}-build-{hash}` | `...-build-3eea25` | `...-build-9e8f54` |
| Dropbox SA | `{org}-{env}-dropbox` | `bigbikedata-dev-dropbox` | `bigbikedata-prod-dropbox` |
| Run SA | `{org}-{env}-run` | `bigbikedata-dev-run` | `bigbikedata-prod-run` |
| Strava SA | `{org}-{env}-strava` | `bigbikedata-dev-strava` | `bigbikedata-prod-strava` |
| Eventarc SA | `{org}-{env}-eventarc` | `bigbikedata-dev-eventarc` | `bigbikedata-prod-eventarc` |
| Dropbox Secret | `{base}-dropbox-secrets` | `bigbikedata-dev-power-core-dropbox-secrets` | `bigbikedata-prod-power-core-dropbox-secrets` |
| JSON Keys Secret | `{base}-fullstack-app-json-keys` | `...-fullstack-app-json-keys` | `...-fullstack-app-json-keys` |
| Artifact Registry | `{base}-docker` | `bigbikedata-dev-power-core-docker` | `bigbikedata-prod-power-core-docker` |
| Public Topic | `{base}-topic` | `bigbikedata-dev-power-core-topic` | `bigbikedata-prod-power-core-topic` |
| Dropbox Topic | `{base}-dropbox-topic` | `...-dropbox-topic` | `...-dropbox-topic` |
| Dropbox Sub | `{base}-dropbox-sub` | `...-dropbox-sub` | `...-dropbox-sub` |
| Eventarc Trigger | `{base}-pubsub-trigger` | `...-pubsub-trigger` | `...-pubsub-trigger` |
| Cloud Run core | `{base}-core` | `bigbikedata-dev-power-core-core` | `bigbikedata-prod-power-core-core` |
| Cloud Run site | `{base}-site-handler` | `...-site-handler` | `...-site-handler` |

where `{base} = {org}-{env}-{app}` (e.g. `bigbikedata-dev-power-core`) and
`{hash} = first 6 chars of sha256({base})`.

**Service accounts** use `{org}-{env}-{purpose}` (not full `{base}`) because GCP
limits SA IDs to 30 chars. E-mail = `{sa}@{project_id}.iam.gserviceaccount.com`.

---

## 4. Step-by-step checklist to build a NEW environment

1. **Copy template:** `cp keys.env.prod.template keys.env.prod` (repo root; or `dev`).
2. **Fill 2 fields:** `MY_USER_ACCOUNT`, `SA_DEPLOYER_EMAIL` (name part only).
   Everything else has a correct deterministic default.
3. **Register external apps** (per-environment, can't be derived):
   - Create a **separate Dropbox App** for this env (dev console).
   - Grab App Key / App Secret; generate Refresh Token (OAuth flow).
   - Strava Client ID / Secret / Refresh Token.
   - Store all of them in the **combined secret** — not in `keys.env`.
4. **Bootstrap:** `./start.sh {env}` (or `--no-welcome` once keys.env exists).
5. **Wire Pub/Sub after first deploy:** `./wire_pubsub.sh {env}`.
6. **Fill the JSON-keys secret** (`fullstack-app-json-keys`) with real values
   from the registry above that are marked secret-layer.
7. **Seed Firestore** doc `config/local/settings/data` with layer-4 keys:
   `CS_BUCKET_NAME`, `GCS_PUB_INPUT_BUCKET`, `GCS_PUB_OUTPUT_BUCKET`,
   `DROPBOX_TOPIC_NAME`, `EMAIL_MODE`, `LOGGING_LEVEL`.
8. Set Cloud Run **env vars**: `GCP_PROJECT_ID`, `APP_JSON_KEYS`, `S_ACCOUNT_RUN`
   (and `ALLOWED_DOMAINS` + `FLASK_SECRET_KEY` on site_handler).

---

## 5. Anti-drift verification

Configuration decays when the three mirrors (README-bootstrap / seeder /
this manifest) disagree. Keep them in sync with:

```bash
# 1. Emulator seeder knows exactly what keys.env SHOULD produce:
python3 -m gcp_actions.emulators.secret_manager.seed --keys-env power_core/keys.env.dev --dry-run

# 2. Dump the live secret in the cloud and diff against the manifest:
gcloud secrets versions access latest \
  --secret=bigbikedata-{env}-power-core-fullstack-app-json-keys \
  --project=bigbikedata-{env}-power-core > /tmp/payload.json
python3 -c "import json;print(sorted(json.load(open('/tmp/payload.json')).keys()))"

# 3. Firestore layer — the boot-time read:
gcloud firestore documents get config/local/settings/data \
  --project=bigbikedata-{env}-power-core
```

Any key present in one layer but missing in another = drift → fix the manifest
and re-seed.

---

## 6. Known quirks (read before debugging)

- `DROpbox_WEBHOOK_PATH` — **odd casing preserved** (lowercase *p*); do not "fix".
- `S_ACCOUNT_RUN` is read by `site_config.py` via the legacy key `s_email_run`
  — the Cloud Run env var supplies both; do not add `SEC_STRAVA`/`s_email_*`
  to new payloads.
- `LOGGING_LEVEL` is **hardcoded to `DEBUG`** in `config.py:90`; the Firestore
  value is read but currently ignored.
- The JSON-keys secret starts with **placeholder values** (bootstrap Stage 6);
  Stage 7 IAM verification only proves *access*, not token correctness.
- Never re-seed from the old `voltaic-bridge-477610-h2` project — its resource
  names belong to a different project.