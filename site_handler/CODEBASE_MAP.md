# Codebase Structure

## Statistics
- Python files: `11`
- Classes: `0`
- Functions: `14`
- Files with parsing errors: `0`

## File: `site_handler/__init__.py`

**Module Description:**
>Site handler service: public-facing Flask frontend for FIT uploads and downloads.

---

## File: `site_handler/main.py`

**Module Description:**
>Entry point for the site_handler service: load config, build the Flask app, and register its blueprints and middleware.

### Standalone Functions
- **`create_app`**: Application factory function.
Initializes Flask application and registers blueprints.
  - **`internal_server_error`**: Render the 500 error page for any unhandled server error.
  - **`class HostRewriteMiddleware`**: WSGI middleware that rewrites the Host header from X-Forwarded-Host for the Firebase Hosting proxy.
    - **`__init__`**: Wrap the given WSGI app instance.
    - **`__call__`**: Rewrite HTTP_HOST/SERVER_NAME/SERVER_PORT from the forwarded host so URL generation uses the public domain.

---

## File: `site_handler/route_site/__init__.py`

**Module Description:**
>Site routes: public access, language selection, and request defense middleware.

---

## File: `site_handler/route_site/app_config_module.py`

**Module Description:**
>Flask SECRET_KEY resolution: environment variable, then local keyring, with hard failure in the cloud.

### Standalone Functions
- **`set_or_get_app_secret`**: Return the Flask SECRET_KEY: from FLASK_SECRET_KEY, else the local keyring, failing hard in the cloud.

---

## File: `site_handler/route_site/defender.py`

**Module Description:**
>Request defense middleware: block direct Cloud Run access and reject any Host not on the allowlist.

### Standalone Functions
- **`extract_hostname`**: Extract hostname from Host header, removing port if present.
Examples:
    'example.com:443' -> 'example.com'
    'example.com' -> 'example.com'
    '127.0.0.1:5000' -> '127.0.0.1'
- **`restrict_direct_access`**: Security Middleware:
Blocks direct access to the 'run.app' URL and enforces the ALLOWED_HOSTS list.

---

## File: `site_handler/route_site/language.py`

**Module Description:**
>Language selection route: persists the chosen locale in the session and redirects to the index page.

### Standalone Functions
- **`set_language`**: Store the requested language in the session (if supported) and redirect to the index page.

---

## File: `site_handler/route_site/public_access.py`

**Module Description:**
>Public-facing frontend routes: landing page, FIT upload to Pub/Sub, download of cleaned files, and success page.

### Standalone Functions
- **`allowed_file`**: Helper to check file extension.
- **`index`**: Serves the index.html file from the application root directory. 
- **`robots_txt`**: Serves the robots.txt file from the static directory. 
- **`handle_file_upload`**: Send user`s file to pipeline by PubSub.
- **`download_file`**: Handles a download request by validating a UUID and generating a short-lived signed URL.
- **`success`**: Shows a confirmation page with a proposal to open the main page again.

---

## File: `site_handler/route_site/tests/debug_link_generation.py`

**Module Description:**
>Diagnostic script: verify the frontend can read a download record and generate a signed GCS URL.

### Standalone Functions
- **`test_generate_signed_url`**: Simulates the frontend reading a record and generating a signed URL.
This test will verify if the service has the correct permissions.

---

## File: `site_handler/utilites/__init__.py`

**Module Description:**
>Utilities for the site handler service: site configuration and localization setup.

---

## File: `site_handler/utilites/babel_config.py`

**Module Description:**
>Babel localization setup for the Flask app and the locale selector used to pick the active language.

### Standalone Functions
- **`get_locale`**: Return the active language: session override, else the best match from the browser's accepted languages.
- **`init_babel`**: Initializes Babel for the Flask app.

---

## File: `site_handler/utilites/site_config.py`

**Module Description:**
>Central configuration for site_handler: environment-derived constants for GCS, Pub/Sub, and allowed domains.

---
