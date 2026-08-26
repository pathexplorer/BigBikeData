# External Services Setup

One-time setup for every external service the BigBikeData platform integrates
with: **Dropbox**, **Wahoo**, **Strava**, **Brevo / SMTP (email)** and **site
hosting (Firebase Hosting + custom domain)**. A separate section covers the
**ngrok** tunnel used for local webhook development.

> **Read this BEFORE the cloud bootstrap.** Every value listed here is a
> per-environment, manually-obtained credential (or account decision) that the
> cloud setup (`main.sh` → `scripts/start.sh`) and runtime configuration
> (`main.sh` → `scripts/configure_runtime.sh`) depend on. Gather them first,
> then provision the cloud project. The full variable registry and storage
> layers live in [`config-manifest.md`](config-manifest.md).
>
> **This document is written for a NEW user spinning up their own project.**
> All concrete names (e.g. `bigbikedata-prod`, `app.bigbikedata.com`,
> `develop@offteleport.cloud`) are the maintainer's examples — substitute your
> own. Each section separates **what YOU must input** from **what the setup
> derives automatically**.

## The big picture

| Service | Where credentials are stored | Env separation |
|---------|------------------------------|----------------|
| **Dropbox** | combined `dropbox-secrets` secret | Separate app + Dropbox account **per environment** |
| **Wahoo** | (account-side only, no stored secret) | One connection per Dropbox account |
| **Strava** | combined `dropbox-secrets` secret + `STRAVA_UPLOAD` toggle in `fullstack-app-json-keys` | Shared app; `STRAVA_UPLOAD=disable` in dev, `enable` in prod |
| **Brevo (email)** | `fullstack-app-json-keys` secret | Shared account, separate `SENDER_EMAIL` per env |
| **SMTP fallback** | `fullstack-app-json-keys` secret | Shared account, separate mailbox/user per env |
| **Site hosting** | custom domain + DNS (provider side); `FRONTEND_BASE_URL` + `ALLOWED_DOMAINS` in `fullstack-app-json-keys`/Cloud Run env | Separate hosting site per env (prod main domain, dev Preview Channel) |
| **ngrok** | `NGROK_AUTHTOKEN` (local only) | Not stored in the cloud |

The rule is *one service account, separate actor per env* (sender / folder /
topic) — not duplicated infrastructure.

---

## 1. Dropbox

The pipeline needs a **separate Dropbox account and app per environment** — real
user data must be isolated.

| Environment | App Name | App's own folder | Watched folder (Wahoo source) | Purpose |
|-------------|----------|------------------|-------------------------------|---------|
| Production  | `bigbikedata-prod` | `/apps/bigbikedata-prod` | `/apps/activities` | Real user data |
| Development | `bigbikedata-dev` | `/apps/bigbikedata-dev` | `/apps/activities` | Test data |

### 1.1 Create a Dropbox App

1. Go to the [Dropbox App Console](https://www.dropbox.com/developers/apps).
2. Click **Create app** → choose **Scoped App**.
3. Choose **Full Dropbox access** — the watched folder (`/apps/activities`)
   lives outside the app's own folder `/apps/<app-name>`, so App Folder access
   would reject reads of it.
4. Set permissions (scopes):
   - `files.metadata.read`
   - `files.metadata.write`
   - `files.content.read`
   - `files.content.write`
5. Use a dedicated Dropbox account for bike files.

> The app must be created as a **Scoped App with Full Dropbox access** so it can
> read files outside its own folder. There must be exactly **one** watched
> folder, and its path can be overridden per environment via
> `DROPBOX_WATCHED_FOLDER`.

### 1.2 Connect Wahoo (one-time per account)

- `Apps` is Dropbox's predefined per-app folder. The Wahoo connection creates a
  folder inside it; after connecting you may **rename** it (this project uses
  `activities`), but there must be exactly **one** watched folder.
- The pipeline watches `DROPBOX_WATCHED_FOLDER`, default `/apps/activities`
  (`power_core/power_core/project_env/config.py`). If you rename the folder,
  update this env var in the deployed service.
- **Renaming a folder with existing files re-triggers a full sync** — Dropbox
  reports every file as re-added, so the pipeline re-processes and re-uploads
  them to Strava (duplicates). Do this before loading data.

### 1.3 Get a Refresh Token

- Dropbox access tokens expire in 10 days (14400 minutes). You need a **refresh
  token** to generate new access tokens automatically.
- In the App Console, generate a refresh token (requires the scopes above).
- Save it securely — it is stored in Google Secret Manager as
  `DROPBOX_REFRESH_TOKEN`.

### 1.4 Configure the Webhook

- In the App Console, set the webhook URI to your Cloud Run service URL plus the
  secret path, e.g. `https://power-core-abc123.run.app/<DROpbox_WEBHOOK_PATH>`.
- `DROpbox_WEBHOOK_PATH` is stored in the `dropbox-secrets` secret and can be
  rotated via the `rotate-webhook` helper.

### 1.5 Local development with ngrok

Dropbox cannot reach `localhost`. See [§ 5](#5-ngrok-local-webhooks-only) for the
public tunnel used by local development.

### 1.6 Variables for this service

| Variable | Required | Meaning | Stored in |
|----------|----------|---------|-----------|
| `DROPBOX_APP_KEY` | Hard | App Key from the Dropbox dev console | `dropbox-secrets` |
| `DROPBOX_APP_SECRET` | Hard | App Secret from the Dropbox dev console | `dropbox-secrets` |
| `DROPBOX_REFRESH_TOKEN` | Hard | Generated via the OAuth refresh-token flow | `dropbox-secrets` |
| `DROPBOX_WATCHED_FOLDER` | Opt | Watched folder path; default `/apps/activities` | service config / `config.py` |
| `DROpbox_WEBHOOK_PATH` | Hard (generated) | Secret webhook path (odd casing — do not "fix") | `fullstack-app-json-keys` |

---

## 2. Strava

The Strava app is **shared across environments**; environments are separated by
the `STRAVA_UPLOAD` toggle.

### 2.1 Create a Strava App

1. Go to the [Strava Developer Console](https://developers.strava.com/).
2. Create an application → note `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET`.

### 2.2 Get a Refresh Token

Strava access tokens expire. Use the token-exchange helper (located at
`power_core/power_core/strava/`):

1. Add to your local keys file:
   ```bash
   STRAVA_CLIENT_ID=your_client_id
   STRAVA_CLIENT_SECRET=your_client_secret
   ```
2. Run `python3 get_refresh_token.py`.
3. Visit `http://localhost:5000/exchange_token`, click **Authorize**, then
   **Authorize** again on Strava.
4. Copy the returned `access_token`, `expires_at`, and `refresh_token`.

> If you re-run with different scopes you get a new refresh token, but previous
> versions remain valid.

### 2.3 Upload toggle per environment

| Variable | prod | dev |
|----------|------|-----|
| `STRAVA_UPLOAD` | `enable` | `disable` (Hard) |

The Strava API requires an active API agreement; dev must never consume it.

### 2.4 Variables for this service

| Variable | Required | Meaning | Stored in |
|----------|----------|---------|-----------|
| `STRAVA_CLIENT_ID` | Opt (Hard if upload enabled) | Strava API client id | `dropbox-secrets` |
| `STRAVA_CLIENT_SECRET` | Opt (Hard if upload enabled) | Strava API client secret | `dropbox-secrets` |
| `STRAVA_REFRESH_TOKEN` | Opt (Hard if upload enabled) | Strava OAuth refresh token | `dropbox-secrets` |
| `STRAVA_UPLOAD` | Opt (dev: Hard `disable`) | Enables/disables the Strava upload stage | `fullstack-app-json-keys` |

---

## 3. Email — Brevo (production) and SMTP fallback

### 3.1 Brevo (primary)

1. Create a [Brevo](https://www.brevo.com/) account.
2. Generate an **API key** (→ `BREVO_API_KEY`). Optionally use a restricted key
   for the dev environment.
3. Configure the sender identity:
   - `SENDER_EMAIL` — the from-address. **Per environment**: dev uses a
     dedicated sender (e.g. `develop@offteleport.cloud`) so dev mail never
     spams from the prod sender.
   - `SENDER_NAME` — the display name.
4. Set `EMAIL_MODE=brevo` per environment.

The sender isolation protects reputation — dev must never send from the
production sender address.

### 3.2 SMTP fallback

Used when `EMAIL_MODE` != `brevo` (e.g. a local/private SMTP relay):

| Variable | Meaning |
|----------|---------|
| `SMTP_SERVER` | SMTP host |
| `SMTP_PORT` | SMTP port |
| `SMTP_SENDER` | From-address for SMTP |
| `SMTP_USER` | SMTP authentication user |
| `SMTP_PASSWORD` | SMTP authentication password |

### 3.3 Variables for this service

| Variable | Required | Meaning | Stored in |
|----------|----------|---------|-----------|
| `EMAIL_MODE` | Opt (`brevo`/`local`) | Email backend switch | `fullstack-app-json-keys` + Firestore |
| `BREVO_API_KEY` | Opt (if brevo) | Brevo API key | `fullstack-app-json-keys` |
| `SENDER_EMAIL` | Opt (if brevo) | From-address (per env) | `fullstack-app-json-keys` |
| `SENDER_NAME` | Opt (if brevo) | From display name | `fullstack-app-json-keys` |
| `SMTP_SERVER/PORT/SENDER/USER/PASSWORD` | Opt (`EMAIL_MODE≠brevo`) | SMTP fallback settings | `fullstack-app-json-keys` |

---

## 4. Site hosting (Firebase Hosting + custom domain)

The public upload portal `site_handler` is served by **Firebase Hosting**, which
forwards requests to the site_handler Cloud Run service. Firebase is a native
Google service, but it is **not provisioned by the GCP bootstrap scripts**: the
hosting site is managed in the Firebase console (or `firebase` CLI), and the
public domain is an environment-specific decision you make. It is therefore
treated like the other manually-prepared services in this document.

> `firebase.json` / `firebase.dev.json` in the repository are **maintainer
> artifacts** — they hardcode THAT project's Cloud Run service ids and domain.
> A new user must **not** copy them verbatim: the rewrite target comes from the
> bootstrap naming convention, and the domain is your own input (see 4.2).

### 4.1 What YOU must decide (user input)

| # | Input | Example | Required | Notes |
|---|-------|---------|----------|-------|
| 1 | **Domain strategy** | custom domain vs free `*.web.app` | Hard | Custom needs a domain whose DNS you can edit |
| 2 | **Custom domain** | `app.yourdomain.com` | if custom | Subdomain of a domain you own |
| 3 | **DNS provider** | Cloudflare / registrar panel | if custom | Where you add the Firebase-issued records |
| 4 | **`FRONTEND_BASE_URL`** | `https://app.yourdomain.com` | Hard | The public URL users open; must match your domain (dev may use the generated `*.web.app` URL) |
| 5 | **`ALLOWED_DOMAINS`** | `app.yourdomain.com,<project>-dev-app-*.web.app,localhost` | Hard | Security allowlist enforced by `site_config.py` |

### 4.2 What the setup derives (no input from you)

- **Firebase hosting site** — created from the same project you bootstrap.
- **Cloud Run rewrite target** — the bootstrap-generated site_handler service
  name (`{org}-{env}-{app}-site-handler`), taken from `CLOUD_RUN_SERVICE_PUB`
  and **injected at deploy time** by `site_handler_run.sh` (the committed
  `firebase.json`/`firebase.dev.json` are just templates and never go stale).
- **Development URL** — the Preview Channel URL (`...-dev-app-*.web.app`),
  printed after deployment and shared for testing.

### 4.3 Custom domain + DNS flow (manual — needs DNS provider access)

1. Add your domain as a **custom domain** in the Firebase console (Hosting).
2. Firebase issues **TXT** (verification) and **A/AAAA** (or CNAME) records.
3. Create those records at your DNS provider (4.1.3).
4. Click **Verify** in the Firebase console — HTTPS is then provisioned
   automatically.
5. Set `FRONTEND_BASE_URL` and `ALLOWED_DOMAINS` to your domain **before**
   running `configure_runtime.sh --apply`.

Simplest dev alternative: skip the custom domain and use the generated Preview
Channel URL as `FRONTEND_BASE_URL`. For a frontend running only on the local
machine, use its local URL instead, e.g. `http://localhost:3000` — fine for
local browser testing, but cannot be used in emails or signed download links
opened from another device.

### 4.4 Variables for this service

| Variable | Required | Meaning | Stored in |
|----------|----------|---------|-----------|
| `FRONTEND_BASE_URL` | Hard | Public frontend URL (per env — your input) | `fullstack-app-json-keys` |
| `ALLOWED_DOMAINS` | Hard | Comma-separated hosted domain allowlist | Cloud Run env (site_handler) |

---

## 5. ngrok (local webhooks only)

Dropbox and the pipeline cannot reach `localhost`; local development exposes a
public tunnel with **ngrok**.

1. Create a free [ngrok account](https://dashboard.ngrok.com/signup) and note
   your auth token.
2. Either export `NGROK_AUTHTOKEN=your_token` or store it in KDE Wallet under
   the key `ngrok`.
3. `./local_dev.sh start` starts the tunnel automatically (prints the public URL
   and the full Dropbox webhook URL to paste into the App Console).
4. To test the webhook challenge: visit
   `https://<ngrok-url>/?challenge=test123` → should return `test123`.

ngrok is a **local-only** dependency; its token is never stored in the cloud.

---

## 6. Pre-flight checklist — gather ALL of this before cloud setup

Before running `./main.sh {env}` (which internally runs
`scripts/start.sh {env}` and `scripts/configure_runtime.sh {env} --apply`),
prepare the following per environment. Values marked **keys.env** belong in
`keys.env.{env}` (next to the virtualenv); the rest go into the Secret Manager
secrets named in **stored in**.

### Credentials to obtain from each provider

| Provider | What to create/obtain | Renv | Variables produced |
|----------|------------------------|------|--------------------|
| Dropbox | One app + account **per env**; scopes; refresh token | `/apps/activities` watched folder | `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN` |
| Wahoo | Connect to each env Dropbox account, rename watched folder to `activities` | – | (account-side, no secret) |
| Strava | One app; client id/secret; refresh token | `STRAVA_UPLOAD=disable` in dev | `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN` |
| Brevo | Account + API key; per-env sender | dev sender != prod sender | `BREVO_API_KEY`, `SENDER_EMAIL`, `SENDER_NAME`, `EMAIL_MODE=brevo` |
| SMTP (optional) | Server credentials, per-env mailbox | – | `SMTP_SERVER/PORT/SENDER/USER/PASSWORD` |
| Hosting | Decide domain strategy (§4.1); add custom domain + DNS + HTTPS (§4.3) | `FRONTEND_BASE_URL` + `ALLOWED_DOMAINS` per env | `FRONTEND_BASE_URL`, `ALLOWED_DOMAINS` |
| ngrok (local) | Free account + authtoken | only local dev | `NGROK_AUTHTOKEN` |

### Sorted by destination secret

| Destination | Values to fill |
|-------------|----------------|
| `keys.env.{dev/prod}` (layer 1) | `MY_USER_ACCOUNT`, `REGION`, `ORG_PREFIX`, `APP_NAME`, `SA_DEPLOYER_EMAIL` (bootstrap-only; see the [bootstrap README](setup_script_README.md)) |
| `dropbox-secrets` (combined) | `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`, `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN` |
| `fullstack-app-json-keys` | `EMAIL_MODE`, `BREVO_API_KEY`, `SENDER_EMAIL`, `SENDER_NAME`, `SMTP_*`, `STRAVA_UPLOAD`, `FRONTEND_BASE_URL`, `DONATION_HTML_SNIPPET_*`, generated keys |
| Cloud Run env (site_handler) | `ALLOWED_DOMAINS`, `GCP_PROJECT_ID`, `APP_JSON_KEYS`, `S_ACCOUNT_RUN` |

> All Dropbox/Strava credentials are stored in the **combined secret** — **not**
> in `keys.env`. Email/hosting values live in `fullstack-app-json-keys`. The
> exact de-storage and payload composition rules are in
> [`config-manifest.md`](config-manifest.md).