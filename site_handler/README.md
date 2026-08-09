# site_handler — Public-Facing Upload Portal

Flask web application that lets users upload .FIT cycling activity files for processing. Sits behind Firebase Hosting with domain-based access control. Deployed on Google Cloud Run.

## Three-Tier Architecture

This project supports **three tiers** of development and deployment (shared with `power_core`):

| Tier | Project | Resources | Use Case |
|------|---------|-----------|----------|
| **Local** | N/A (emulators) | Podman: Secret Manager, Firestore, Pub/Sub | Daily development, fast iteration, debugging |
| **Dev** | `bigbikedata-dev` | Real GCP (isolated, test data) | Integration testing, Cloud Run behavior, real webhooks |
| **Prod** | `bigbikedata` | Real GCP (production data) | Live users, real billing |

## How It Works

```
User ──► Firebase Hosting ──► site_handler (Cloud Run) ──► Pub/Sub ──► power_core (Backend)
            │                        │
            │                        └──► Short-lived signed URL for download
            │
            └── Security redirects for common attack patterns
```

1. **User visits** the website (served via Firebase Hosting)
2. **Uploads** a .FIT file and provides their email
3. **Frontend publishes** the file content to a Pub/Sub topic
4. **Backend** (`power_core`) processes the file asynchronously
5. **User receives** an email with a download link to the cleaned file

## Features

- **File Upload** — drag-and-drop / form-based upload of .FIT files (`.fit` only)
- **Email Notifications** — users get notified when processing is complete
- **Short-lived Download Links** — signed GCS URLs with 1-minute TTL, expiration tracking in Firestore
- **Internationalization** — English (`en`) and Ukrainian (`uk`) via Flask-Babel
- **Security Middleware** — restricts access to an allowlist of domains, blocks direct Cloud Run URL access and bots
- **Firebase Hosting** — extensive `.json` configuration with rewrites and security redirects (blocks `/wp-*`, `/admin`, `.env`, and 30+ common attack patterns)
- **Tailwind CSS** — styling via Tailwind CSS v4

## Project Structure

| Path | Purpose |
|------|---------|
| `site_handler/main.py` | Flask app factory, blueprint registration, proxy middleware |
| `site_handler/route_site/public_access.py` | Main routes: `/`, `/upload`, `/download/<id>`, `/success` |
| `site_handler/route_site/defender.py` | Security middleware — domain allowlist enforcement |
| `site_handler/route_site/language.py` | Language switcher routes (`/language/<lang>`) |
| `site_handler/route_site/app_config_module.py` | App secret key management |
| `site_handler/utilites/babel_config.py` | Flask-Babel initialization and locale configuration |
| `site_handler/utilites/site_config.py` | Environment variable loading for the frontend |
| `site_handler/templates/` | Jinja2 templates (`index.html`, `success.html`, `500.html`, `404_expired.html`) |
| `site_handler/static/` | Static assets (CSS, JS, favicon, robots.txt, 404 fallback) |

## Configuration

| Variable | Description |
|----------|-------------|
| `GCP_TOPIC_NAME` | Pub/Sub topic to publish uploads to |
| `ALLOWED_DOMAINS` | Comma-separated list of allowed hostnames |
| `FLASK_SECRET_KEY` | Flask session secret (loaded from Secret Manager) |
| `S_ACCOUNT_RUN` | Service account for signed URL generation |

## Local Development

```bash
# Set up virtual environment
cd site_handler
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Install and build Tailwind CSS
npm install
npx @tailwindcss/cli -i ./site_handler/static/css/input.css -o ./site_handler/static/css/output.css

# Run (listens on port 8080 by default)
python site_handler/main.py
```

## Internationalization

Translations use Flask-Babel with compiled `.mo` files in `site_handler/translations/`.

```bash
# Extract strings
pybabel extract -F babel.cfg -o messages.pot .

# Initialize a new language
pybabel init -i messages.pot -d translations -l uk

# Compile after translation
pybabel compile -d translations
```

## Deployment

### Auto-detect from Branch (Recommended)
```bash
# From main/master branch → deploys to PROD
./site_handler_run.sh

# From feature branch → deploys to DEV
./site_handler_run.sh
```

### Explicit Environment
```bash
# Force production deployment
./site_handler_run.sh prod

# Force development deployment
./site_handler_run.sh dev
```

### How It Works
| Branch | Auto-detected Env | Cloud Run Service | Firebase Config | Keys File |
|--------|-------------------|-------------------|-----------------|-----------|
| `main` / `master` | `prod` | `site-handler` | `firebase.json` | `keys.env.prod` |
| `feature/*`, `fix/*`, etc. | `dev` | `site-handler-dev` | `firebase.dev.json` | `keys.env.dev` |

The script auto-detects the environment from the current Git branch:
- **`main` or `master`** → Production (Firebase main domain)
- **Any other branch** → Development (Firebase Preview Channel)

### Firebase Configuration

| Environment | Firebase Config | Cloud Run Service | URL |
|-------------|-----------------|-------------------|-----|
| **Production** | `firebase.json` | `site-handler` | `https://app.bigbikedata.com` |
| **Development** | `firebase.dev.json` | `site-handler-dev` | `https://bigbikedata--dev-app-*.web.app` |

The preview channel URL is printed after deployment. Share it for testing.

## Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Main upload page (`index.html`) |
| `/upload` | POST | Handle file upload and publish to Pub/Sub |
| `/download/<uuid>` | GET | Generate short-lived signed URL for download |
| `/success` | GET | Upload success confirmation page |
| `/language/<lang>` | GET | Switch language (`en` or `uk`) |
| `/robots.txt` | GET | Static robots.txt |
