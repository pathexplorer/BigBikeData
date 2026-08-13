# Codebase Structure

## Statistics
- Python files: `32`
- Classes: `5`
- Functions: `45`
- Files with parsing errors: `0`

## File: `power_core/__init__.py`

**Module Description:**
>Power core service: FIT/GPS data processing, Dropbox sync, Strava upload, and email notifications.

---

## File: `power_core/database/__init__.py`

**Module Description:**
>Database connectivity and streaming ingestion for the power core service.

---

## File: `power_core/database/db_conect.py`

**Module Description:**
>PostgreSQL connectivity and streaming ingestion helpers built on Psycopg 3.

### Standalone Functions
- **`connect_to_db`**: Establishes a connection to the PostgreSQL database.
- **`load_stream_to_postgres`**: Streams data directly into PostgreSQL using Psycopg 3's efficient copy writer.

---

## File: `power_core/dropbox_usage/__init__.py`

**Module Description:**
>Dropbox integration: authentication, watched-folder sync, and file uploads.

---

## File: `power_core/dropbox_usage/get_from_dropbox.py`

**Module Description:**
>Dropbox sync entry point: list watched-folder changes and publish pointers to new FIT files to Pub/Sub.

### Classes
- **`class DropBoxCursor`**: Persists the Dropbox sync cursor in Firestore so incremental listing continues where it left off.
  - **`__init__`**: Point the cursor store at the Firestore document identified by db_cursor_doc.
  - **`load_cursor`**: Return the stored Dropbox cursor, or None on the first run.
  - **`save_cursor`**: Persist the given cursor, or clear the document when it is empty.

### Standalone Functions
- **`connect_to_dropbox`**: Incrementally list the watched Dropbox folder and publish each new FIT file to Pub/Sub.

---

## File: `power_core/dropbox_usage/local/get_secr.py`

**Module Description:**
>Initializing Dropbox App
For local run

### Standalone Functions
- **`index`**: Redirect to the Dropbox OAuth consent screen to obtain an authorization code.
- **`oauth_callback`**: Exchange the OAuth code for tokens and persist the refresh token in Secret Manager.

---

## File: `power_core/dropbox_usage/upload_to_dropbox.py`

**Module Description:**
>Stream files from a GCS folder into Dropbox using resumable upload sessions.

### Standalone Functions
- **`upload_custom_files_session`**: Upload every blob under the given GCS folder to Dropbox via resumable sessions, returning the uploaded paths.

---

## File: `power_core/dropbox_usage/utils.py`

**Module Description:**
>Dropbox authentication helpers: inject credentials from Secret Manager and authorize the Dropbox client.

### Classes
- **`class DropboxAuth`**: Loads Dropbox credentials from Secret Manager and provides the authorized client and signature checks.
  - **`__init__`**: Inject the Dropbox/Strava secrets from Secret Manager into the environment and preflight the DB.
  - **`auth_dropbox`**: Creates and authorizes a Dropbox client.
This is the single source of truth for Dropbox authentication.
  - **`check_signature`**: Verify the HMAC webhook signature of the current request, returning True or a 403 response.

---

## File: `power_core/heatmap_gpx/__init__.py`

**Module Description:**
>Heatmap generation: appends activity GPX fragments into aggregated heatmap files.

---

## File: `power_core/heatmap_gpx/append_function.py`

**Module Description:**
>Append one file to one in binary mode for economy
After all, delete an original GPX file of activity

### Standalone Functions
- **`extract_first_time_tag`**: Return the first <time> value found in a GPX file, or None if absent.
- **`strip_source_content`**: Strip the GPX header/footer in place, leaving only track content ready for concatenation.
- **`append_gpx_via_compose`**: Append a stripped GPX fragment to the bike's heatmap via GCS compose, rolling to a new version at the 32-compose cap.

---

## File: `power_core/heatmap_gpx/local/closer.py`

**Module Description:**
>Adding closer tag to heatmap file before direct using in OSM or JOSM
Work locally

### Standalone Functions
- **`check_if_exist`**: Check the last lines of a GPX file for a closing tag, appending it when missing.
- **`add_closer`**: Append the GPX closing tag to the given file.

---

## File: `power_core/main.py`

**Module Description:**
>Entry point for the power_core service: load config, pre-flight check secrets, and serve the transfer Flask API.

### Standalone Functions
- **`_verify_secrets`**: Pre-flight check: fetch every critical secret and confirm required keys exist, exiting the process on any failure.
- **`create_app`**: Build and return the Flask application with all transfer blueprints registered.

---

## File: `power_core/postgis/fitcsv.py`

**Module Description:**
>Extract track points from FIT files and serialize them to CSV for downstream ingestion.

### Standalone Functions
- **`extract_track_points`**: Parse 'record' messages from a FIT file into a list of timestamp/latitude/longitude dicts (degrees).
- **`save_to_csv`**: Write track points to a CSV file keyed on the first record's fields; no-op when empty.

---

## File: `power_core/project_env/__init__.py`

**Module Description:**
>Project environment: configuration loading and local development helpers.

---

## File: `power_core/project_env/config.py`

**Module Description:**
>Central configuration for power_core: loads env-derived constants and fails fast when required variables are missing.

---

## File: `power_core/project_env/inspect_env.py`

**Module Description:**
>Script runs after open the project and shows current variables

### Standalone Functions
- **`get_env_vars_from_file`**: Reads a .env file and returns a set of variable names defined within it.
- **`inspect_loaded_vars_table`**: Compares file variables to the active Python environment and prints them
in a two-column table format.

---

## File: `power_core/project_env/local/checking_env.py`

**Module Description:**
>Deprecated local environment checking; superseded by the pre-flight checks in project_env.config.

---

## File: `power_core/project_env/local/expanding_path.py`

**Module Description:**
>Deprecated path expansion helper; superseded by Path().expanduser() usage in project code.

---

## File: `power_core/routes/__init__.py`

**Module Description:**
>HTTP routes for the power core service: Dropbox webhooks and Pub/Sub processing endpoints.

---

## File: `power_core/routes/pubsub_handler.py`

**Module Description:**
>Shared Pub/Sub push handler that decodes, validates, deduplicates, and routes messages to the activity pipelines.

### Standalone Functions
- **`check_and_mark_processed`**: Deduplicate Pub/Sub messages via a Firestore idempotency marker; True means already processed.

Fails closed (True) when the DB check errors, so malformed messages don't trigger infinite retry loops.
- **`execute_pipeline`**: Run the pipeline method and record completion/failure status in Firestore.

Returns a 200 to Pub/Sub on processing errors so logic bugs are acknowledged instead of retried forever.
- **`handle_message`**: Entry point for Pub/Sub push subscriptions: decode, validate, deduplicate, and route a message to its pipeline strategy.

---

## File: `power_core/routes/transfer.py`

**Module Description:**
>Flask blueprints exposing the power_core HTTP endpoints: Dropbox webhook sync, Pub/Sub processing, and file upload.

### Standalone Functions
- **`dropbox_webhook`**: PRODUCER endpoint: verify Dropbox signature, then trigger the sync process.
- **`webhook_verification`**: Echo back the challenge param to confirm webhook ownership.
- **`handle_pubsub_message`**: Process public Pub/Sub push messages via shared pipeline handler.
- **`handle_private_message`**: Process private Pub/Sub push messages via shared pipeline handler.
- **`trigger_upload`**: Trigger a custom-file session upload for a given GCS folder.

---

## File: `power_core/strava/__init__.py`

**Module Description:**
>Strava integration: OAuth2 token management and activity upload.

---

## File: `power_core/strava/auth.py`

**Module Description:**
>Strava OAuth2 token management: refresh the access token before it expires and persist it back to Secret Manager.

### Standalone Functions
- **`update_strava_token_if_needed`**: Return the current Strava access token, refreshing it via the persistent refresh token when close to expiry.

---

## File: `power_core/strava/local/get_refresh_token.py`

**Module Description:**
>Base setting for first run

### Standalone Functions
- **`home`**: Render the Strava OAuth authorization link for the first token exchange.
- **`exchange_token`**: Exchange the OAuth authorization code for access and refresh tokens.

---

## File: `power_core/strava/upload.py`

**Module Description:**
>Upload cleaned FIT activities to Strava and associate them with a gear (bike) model.

### Classes
- **`class StravaUpload`**: Uploads a FIT activity to Strava and assigns the detected bike as its gear.
  - **`__init__`**: Store the Strava bearer token, local FIT path, and the gear id to attach.
  - **`_upload_fit_to_strava`**: Upload the local FIT file and return the Strava upload id.
  - **`_poll_upload_status`**: Poll the upload status until Strava returns the resulting activity id (20s cap).
  - **`upload_activity`**: Upload the activity and attach the bike gear id; returns the updated activity and its id.

---

## File: `power_core/utilites/__init__.py`

**Module Description:**
>Utilities for the power core service, such as email delivery.

---

## File: `power_core/utilites/email_sender.py`

**Module Description:**
>Email sending with pluggable backends: local SMTP for development and the Brevo API for production.

### Standalone Functions
- **`_send_email_smtp`**: Sends an email using a standard SMTP server.
It supports both the simple local debugger and real SMTP servers like Gmail.
- **`_send_email_brevo`**: Sends an email using the Brevo API, for production.
- **`send_email`**: Sends an email using either a local SMTP server or the Brevo API,
based on the EMAIL_MODE environment variable.

---

## File: `power_core/workshop/__init__.py`

**Module Description:**
>Workshop: FIT/CSV processing instruments, activity pipelines, and database ingestion.

---

## File: `power_core/workshop/csv_to_base.py`

**Module Description:**
>GPS Data Processor (Memory Stream to PostgreSQL)
Target: Psycopg 3 (Modern Python)

### Classes
- **`class DataProcessingError`**: Raised when raw CSV values cannot be parsed into a valid GPS record.

### Standalone Functions
- **`convert_semicircles_to_degrees`**: Convert a FIT semicircle coordinate value into decimal degrees.
- **`convert_garmin_timestamp`**: Convert a Garmin epoch (1989-12-31) seconds value into an ISO-8601 timestamp string.
- **`parse_memory_csv_stream`**: Yields parsed rows one by one. No large lists created in memory.
- **`process_data`**: Stream parsed GPS rows from the raw CSV string into PostgreSQL.

---

## File: `power_core/workshop/instruments.py`

**Module Description:**
>FIT/CSV processing instruments: conversion, GPS cleaning, bike labeling, and user notification emails.

### Standalone Functions
- **`is_safe_tmp_path`**: Validates that a filepath is:
1. Absolute and located inside /tmp
2. Has a safe filename (alphanumeric, dots, dashes, underscores, AND SPACES)
3. Ends with .fit or .csv
4. Does not begin with a dot; does not contain suspicious dot patterns
5. Contains only printable ASCII characters
- **`convert_fit_to_csv`**: Converts a .fit file to .csv or vice versa using the FitCSVTool.jar.
It uses an absolute path to the .jar file to ensure it runs correctly
in any environment (local or container).
- **`label_bike`**: Return the Strava gear id matching the first known ANT sensor number in the stream, or a stopgap id.
- **`clean_data_stream`**: Yield each streamed line cleaned of negative latitudes and fixed serial numbers, with a validation flag and change count.
- **`cleaner_run`**: Stream-clean a FIT CSV for the given pipeline, saving the fixed file only when needed, and return the detected bike id and issue count.
- **`load_email_template`**: Load the localized subject and body email templates for the given clean result, defaulting to English.
- **`write_email_with_link`**: Notify the user about their cleaned FIT: email a download link when found, or a warning when not.
- **`extract_points_from_csv_string`**: Parses a string containing CSV data and extracts track points.
Assumes the CSV has 'latitude', 'longitude', and 'timestamp' columns.
- **`extract_track_points_from_fit`**: Parse 'record' messages from a FIT file into timestamp/latitude/longitude dicts, converting semicircles to degrees.
- **`save_to_csv`**: Write track points to a CSV file keyed on the first record's fields; no-op when empty.

---

## File: `power_core/workshop/tests/debug_link_creation.py`

**Module Description:**
>Debug utilities for generating download links in the workshop pipeline.

---

## File: `power_core/workshop/workers.py`

**Module Description:**
>Activity processing pipelines: orchestrate FIT download, GPS cleaning, re-encoding, emailing, and Strava upload.

### Classes
- **`class ActivityProcessingPipeline`**: Orchestrates the multi-stage processing of a .FIT activity file.

Can be triggered from GCS, an HTTP request with file data, or a Pub/Sub message with a Dropbox path.
  - **`__init__`**: Initializes the pipeline with a source filename, optional raw file bytes, or a Dropbox path.

The `pipeline_type` selects the filename strategy: 'private' keeps the original
name while 'public' uses a unique ID to avoid GCS collisions.
  - **`stage_01_download_fit`**: Downloads the original .FIT file from Dropbox
or writes it from memory if file_data is present.
  - **`stage_02_fit_to_unexplored_csv`**: Decodes the local .FIT file into an 'unexplored' CSV for GPS cleaning.
  - **`stage_03_clean_gps_data`**: Cleans GPS problems in the unexplored CSV and captures the detected bike model.

Uploads the fixed CSV to GCS only when issues were found or the private pipeline runs.
  - **`stage_04_fixed_csv_to_fit`**: Re-encodes the fixed CSV back into a clean .FIT file and uploads it to GCS.
  - **`stage_04_01_email_cleaned_fit`**: Emails the user a download link for the cleaned FIT, based on the clean result.
  - **`stage_05_upload_to_strava`**: Uploads the cleaned FIT file to Strava if the environment switch is 'prod'.
Also updates the activity's gear/bike model.
  - **`stage_06ver2_create_parce_csv`**: Builds a parsed CSV from the cleaned data for PostgreSQL ingestion (placeholder stage).
  - **`stage_07ver2_load_in_postgresql`**: Loads the parsed CSV rows into PostgreSQL (placeholder stage).
  - **`run_full_pipeline`**: Executes every stage of the private activity processing pipeline with timing.
  - **`run_repair_flow`**: Executes the public-facing repair flow for users.

---
