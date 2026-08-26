# BigBikeData — Tech Lead Review

**Reviewer:** Tech Lead (Data Engineering & Infrastructure)  
**Project:** BigBikeData — FIT file GPS teleportation cleaning, Strava upload, and heatmap pipeline  
**Date:** July 2026

---

## 1. Project Overview & Architectural Summary

BigBikeData is a two-service monorepo that processes cycling `.FIT` files from Garmin devices. It detects and removes GPS "teleportation" artifacts, re-encodes clean files, uploads them to Strava, and optionally builds GPX heatmaps.

### System Architecture

```
User ──► site_handler (Public Cloud Run)
            │
            │ FIT file (multipart upload)
            ▼
         Pub/Sub topic
            │
            ▼
      power_core (Private Cloud Run)
            │
            ├── Stage 1: Download FIT (Dropbox or direct upload)
            ├── Stage 2: FIT → CSV (FitCSVTool.jar / Java)
            ├── Stage 3: Clean GPS data (streaming regex + negative lat removal)
            ├── Stage 4: CSV → FIT (re-encode)
            ├── Stage 5: Upload to Strava (API)
            ├── Stage 6: PostGIS load (disabled / commented out)
            └── Stage 7: Heatmap build (disabled / commented out)
```

- **site_handler** — Public-facing Flask app. Users upload `.FIT` files; the service publishes messages to Pub/Sub and emails download links via Brevo/SMTP with signed GCS URLs (1-minute TTL).
- **power_core** — Internal Flask app. Consumes Pub/Sub messages, runs the multi-stage pipeline, persists track points to PostgreSQL (PostGIS), updates heatmaps in GCS, and uploads clean files to Strava.
- **State store:** Firestore for idempotency keys (`processed_messages`, `dropbox_messages`), download-link metadata, heatmap version tracking, and Dropbox sync cursors.
- **Secrets:** Google Secret Manager for Strava tokens, Dropbox tokens, and service account keys.
- **CI/CD:** Google Cloud Build with two separate pipelines + custom shell scripts.

The architecture is fundamentally **sound**. Two independently deployable services communicating asynchronously via Pub/Sub is a solid pattern for an event-driven batch pipeline. The application factory pattern (Flask `create_app()`) is used correctly in both services, enabling proper config lifecycle management.

---

## 2. Data Engineering & Architectural Concept Matrix

| Engineering Concept | Implementation Method | Tech Lead's Review / Critique |
|---|---|---|
| **Idempotency** | Firestore documents with `idempotency_key`, `SERVER_TIMESTAMP`, and TTL. Fail-safe returns `True` (assume duplicate) on DB errors. | **Solid design.** The fail-safe default prevents infinite Pub/Sub retries during Firestore outages — correct engineering decision. TTL-based expiration is production-grade. |
| **Streaming / Generator Pattern** | `clean_data_stream()` yields cleaned lines; `parse_memory_csv_stream()` yields parsed rows. PostgreSQL uses `psycopg` 3's streaming `copy.write_row()`. | **Advanced implementation.** Avoids loading entire files into memory. The generator chain (file → clean → parse → PG COPY) is the right approach for files that could be hundreds of MB. |
| **CDC & Incremental Sync** | Dropbox `files_list_folder_continue` with cursor persisted in Firestore (`cursors/db_cursor`). | **Correct.** Efficient delta sync rather than full re-scan. Cursor state is properly externalized (not local), so it survives container restarts. |
| **File Security / Temp Validation** | Path is validated against `/tmp` with strict regex: alphanumeric only, no `..`, no non-ASCII, `.fit`/`.csv` extension only. | **Excellent.** This is a real production concern — Path Traversal via user-supplied filenames is a common vulnerability. The multilayered validation (resolve symlinks + pattern + dot/extension checks) is thorough. |
| **GCS Object Composition** | Heatmap built by composing existing GCS blobs server-side (up to 32 per composition), with version rotation. | **Master-level GCS optimization.** No need to download/upload large files — server-side compose is far cheaper and faster. Version rotation avoids the 32-component limit correctly. |
| **Error Handling in Pub/Sub** | Logic errors return `200` to Pub/Sub to acknowledge the message and stop retries; Firestore status documents track `completed`/`failed` states. | **Advanced.** Distinguishes between recoverable (transient) and unrecoverable (logic) errors. Dead-message detection is possible by querying `status == 'failed'` documents. |
| **Email Multi-Provider Routing** | `EMAIL_MODE` env var switches between Brevo API and local SMTP. Graceful fallback with logging. | **Design is correct.** The routing is clean, and the `try/except` for optional Brevo SDK import is pragmatic. |
| **Security Middleware** | `defender.py` blocks direct `run.app` access, enforces domain allowlist via `Host` and `X-Forwarded-Host` headers. | **Production-grade security.** Prevents bot cold-start attacks and host-header injection. The dual-header check (Host + X-Forwarded-Host) is necessary behind Firebase Hosting. |
| **Heatmap / PostGIS Stages** | `stage_06ver2_create_parce_csv` and `stage_07ver2_load_in_postgresql` are **empty stubs**. GPX/heatmap stages are commented out. | **Pipeline is incomplete.** The spatial database and heatmap features are not wired up. This is either WIP or legacy code that was disabled. Either way, it should be removed or marked explicitly as "planned." |
| **Automated Testing** | No `pytest` tests. No `conftest.py`. Two debug scripts exist (one empty, one manual). `_local_tests/` is scratch files. | **Critical gap.** Zero automated test coverage for a pipeline with 5+ external API integrations (Dropbox, Strava, GCS, Firestore, Pub/Sub, PostgreSQL, Brevo) is a significant production risk. |

---

## 3. Technology Proficiency Matrix

| Technology / Tool | Assessed Level | Concrete Evidence in Code/Architecture |
|---|---|---|
| **Python 3.12** | **Advanced** | Generator-based streaming for large file processing; proper use of `pathlib.Path.resolve()` for security; `datetime.UTC` (3.12+); type hints with `Generator` and `Literal`; `NamedTemporaryFile` with explicit cleanup in `except`/`finally` patterns. |
| **Flask** | **Advanced** | Application factory pattern with lazy imports inside `create_app()`; blueprint-based route separation; custom WSGI middleware (`HostRewriteMiddleware`); `ProxyFix` integration; global error handler (`@flask_app.errorhandler(500)`). |
| **Google Cloud Pub/Sub** | **Advanced** | Idempotency layer with Firestore; base64 payload handling with proper error/validation; dual-pipeline routing (`PIPELINE_CONFIG` strategy pattern); Firestore status tracking for completed/failed messages. |
| **Google Cloud Firestore** | **Advanced** | `SERVER_TIMESTAMP` for distributed clock consistency; TTL-based document expiration; transactional idempotency check; multi-collection usage (messages, download_links, heatmap, cursors). |
| **Google Cloud Storage (GCS)** | **Master** | Object composition for heatmap building (server-side blob merging, 32-component limit handling); signed URLs with 1-minute TTL for secure downloads; version-aware blob management. |
| **Google Secret Manager** | **Advanced** | Strava OAuth tokens persisted and refreshed in-place in Secret Manager; `InjectConfig` loads secrets before Flask app creation; distinct secrets for Dropbox, Strava, and service accounts. |
| **PostgreSQL / PostGIS** | **Base** | `psycopg` 3 streaming `COPY` is the right choice, but the pipeline stage that uses it is an empty stub; the PostGIS integration is incomplete and untested. |
| **Docker / Cloud Build** | **Advanced** | Multi-stage Docker build (builder → runtime, JRE only in final image); `python:3.12-slim` with minimal `apt` packages; `--no-cache-dir`, `--disable-pip-version-check` best practices; Cloud Build with `ALLOW_LOOSE` substitutions. |
| **Shell Scripting (IaC)** | **Master** | Comprehensive 12-stage GCP project bootstrap (`docs/scripts/startup/start.sh`) covering project creation, API enablement, SA creation with least-privilege IAM, secrets, Pub/Sub, Artifact Registry, Firestore, VPC networking. Modularized into `lib/` and `addons/` with reusable functions. |
| **JavaScript (Frontend)** | **Advanced** | ES modules (`type="module"`); clean separation of concerns (`main.js` → `file_handler.js` → `utils.js`); proper `DOMContentLoaded` lifecycle management; `fetch` with `FormData` for file upload. |
| **Java (FitCSVTool.jar)** | **Base** | Invoked via `subprocess.run(command, check=True)`. The JAR is vendored in the repo. No Java code is written by the candidate — the tool is consumed as a binary dependency. |
| **Flask-Babel (i18n)** | **Advanced** | Full Ukrainian + English translation support with compiled `.mo` files; locale detection from request/language cookie; proper `.po`/`.mo` workflow. |

---

## 4. Practical Code & Architecture Improvements

### 🔴 Critical (Fix Immediately)

| # | Issue | Location | Impact |
|---|-------|----------|--------|
| **C1** | **Strava upload is dead code.** `upload_id = self._upload_fit_to_strava` (line 28) assigns the *method object* to `upload_id` instead of calling it. Same bug on line 45: `activity_id = self._poll_upload_status`. The `_upload_fit_to_strava` method is never executed. | `power_core/power_core/strava/upload.py` | **Strava integration produces a `TypeError` at runtime.** Every pipeline run that hits Stage 5 will crash. This is a silent breakage — if `STRAVA_UPLOAD=disable`, it's hidden. |
| **C2** | **Warning email templates will crash with `KeyError`.** Templates use `{donation_section_privat}` (missing 'e') but the code context dict uses key `"donation_section_private"` (with 'e'). | `templates/warning_email/en_body.html` line 15, `templates/warning_email/uk_body.html` line 13 vs `instruments.py` line 342 | Any "no issues found" email will fail `str.format()` with `KeyError`. The email feature is broken for this code path. |
| **C3** | **`APP_JSON_KEYS` passed as plain env var in Cloud Build.** The substitution `--set-env-vars=APP_JSON_KEYS=${_APP_JSON_KEYS}` exposes service account JSON keys in Cloud Build logs and process listings. | `cloudbuild.yaml` line 28, `main.py` line 11 | Credential leakage. Service account keys should be loaded from Secret Manager at runtime, not injected via env var substitutions. |

### 🟡 Next Steps (Architecture & Production Hardening)

| # | Issue | Recommendation |
|---|-------|---------------|
| **N1** | **Zero automated tests.** No unit, integration, or end-to-end tests for any pipeline stage. | Add a `tests/` directory with pytest. At minimum: (1) unit tests for `clean_data_stream()` with sample CSV data; (2) integration test for the Pub/Sub handler with a local emulator; (3) mock-based test for the full pipeline. The `gcp_actions` package should have test doubles for GCS/Firestore. |
| **N2** | **Heatmap and PostGIS stages are dead stubs.** `stage_06ver2_create_parce_csv` and `stage_07ver2_load_in_postgresql` are empty; GPX/heatmap pipeline stages are commented out. | Either finish these stages or delete them. Dead code confuses future maintainers and signals that the architecture docs don't match the running system. If they are planned but not built, leave a `TODO` with a ticket reference. |
| **N3** | **Local dependency on private `gcp_actions` package.** `requirements.txt` contains `-e /home/stas/projects/main/gcp_actions` — an absolute path on your dev machine. | Move `gcp_actions` to a private PyPI repository (e.g., Artifact Registry) or vendor it in the monorepo at a fixed path that both Dockerfiles reference. The current Dockerfiles work because they `COPY ./gcp_actions ./gcp_actions`, but the editable install in `requirements.txt` is non-portable. |
| **N4** | **`cleaner_run()` reads the input file twice.** Once for `label_bike()` and once for `clean_data_stream()`. For multi-GB files, this doubles I/O. | Extract the bike label from the header of the CSV in a single pass, or interleave labeling into the cleaning generator. Since `label_bike` returns on first match, a header-only read would suffice. |
| **N5** | **No data quality monitoring or alerting.** No metrics on bad-line counts, pipeline failures, or processing latency. | Add structured logging with severity-based alerting in Cloud Logging. At minimum: alert on `status == 'failed'` in Firestore; track `bad_lines` distribution; monitor Pub/Sub backlog age for the pipeline subscription. |
| **N6** | **No data retention policy for PostgreSQL.** Track points table has no partitioning or archival strategy. | Add time-based partitioning on the timestamp column if the table is active. Implement a retention window (e.g., 90 days) with a cleanup job via Cloud Scheduler. |
| **N7** | **Readability: `utilites/` typo in both services.** The package directory is misspelled (should be `utilities/`). | Rename for consistency. While cosmetic, it suggests the codebase lacks a review pass. |

### 🧹 Portfolio Cleanup

| File | Action | Reason |
|------|--------|--------|
| `power_core/_local_tests/*` | Remove from committed repo, add to `.gitignore` | Scratch/experimental scripts (CRC calculator, wordlist generator, variable scope test) clutter the repo. They should live in a scratch directory outside version control. |
| `power_core/power_core/project_env/local/checking_env.py`, `expanding_path.py` | Delete | Empty/commented-out files. Dead code. |
| `power_core/power_core/workshop/tests/debug_link_creation.py` | Either implement tests or delete | Empty file. A `tests/` directory should contain actual tests. |
| Commented-out heatmap/GPX stages in `workers.py` (lines 205–223) | Remove or uncomment | Six-month-old commented code erodes trust in the codebase. Either wire it up or document it externally. |
| Commented-out imports and Pandas/SQLAlchemy code in `db_conect.py` | Remove | Dead code paths from a refactor. |

---

## 5. Tech Lead's Recommended Interview Questions

These questions probe beyond "what does this code do" and test whether the candidate understands the trade-offs they made and could defend them in a production environment.

### Q1: Strava Upload Bug

> In `power_core/strava/upload.py` on line 28, you wrote `upload_id = self._upload_fit_to_strava`. What does this line actually do at runtime? What would happen when `_poll_upload_status()` runs, and what is the fix?

**What to look for:** The candidate should immediately identify that `.method_name` without `()` assigns the method object (a bound method reference), not the return value. They should explain that `_upload_fit_to_strava` is never called, so `upload_id` is a method, not an integer — the subsequent `requests.get(url, upload_id)` will either concatenate a method to the URL string (via `__str__`) or raise `TypeError`. The fix is `upload_id = self._upload_fit_to_strava()`. Bonus points if they notice line 45 has the same bug.

### Q2: Idempotency Fail-Safe Trade-off

> Your `check_and_mark_processed()` function returns `True` (assumes duplicate) if Firestore is unreachable. This prevents infinite Pub/Sub retries during a Firestore outage. But it also means a genuine new message could be silently dropped during that window. Walk me through how you'd mitigate data loss in this scenario without breaking the retry-safety guarantee.

**What to look for:** A strong candidate will acknowledge the trade-off and propose:
- A dead-letter queue (DLQ) for messages that hit the idempotency failsafe — re-queue them once Firestore is healthy.
- Retry with exponential backoff for transient DB errors before falling back to "assume duplicate."
- A reconciliation job that periodically scans Firestore and the Pub/Sub subscription for unprocessed or orphaned messages.
- Changing the default to `False` (assume new, risk duplicate) for a public-facing service where data loss is worse than duplicates, and rely on downstream dedup in PostgreSQL/Strava.

### Q3: Streaming CSV Processing Security

> Your `is_safe_tmp_path()` function has 5 layers of path validation. Walk me through a realistic attack where a user-supplied filename could bypass the first 3 layers but get caught by the 4th or 5th. Then tell me: is there a scenario where an attacker could still write outside `/tmp` despite all these checks?

**What to look for:** They should understand each layer:
1. `Path.resolve()` catches symlink tricks and `../` traversal.
2. `is_relative_to(tmp_dir)` catches absolute paths outside `/tmp`.
3. Regex validates character set.
4. `..` check and single-dot check catches obvious traversal.
5. ASCII range check catches null bytes or encoding tricks.

For a bypass: symlink at `/tmp/foo → /etc/passwd` would pass layers 1–2 but would be caught by extension check (not `.fit`/`.csv`). A truly security-aware candidate might note that `/tmp` on a multi-tenant container could have race conditions (TOCTOU between validation and open) — not exploitable in single-container Cloud Run but worth calling out.

### Q4: Pipeline Stage Orchestration vs. Pub/Sub

> Right now your multi-stage pipeline is a synchronous chain of method calls inside a single Pub/Sub subscriber. If Stage 5 (Strava upload) takes 30 seconds because Strava is slow, your entire Cloud Run instance is blocked and can't process other messages. How would you decouple the stages so they can scale independently?

**What to look for:** The candidate should recognize this as a classic orchestration vs. choreography question. Strong answers include:
- **Event-driven fan-out:** Each stage publishes its output to a distinct Pub/Sub topic, with dedicated subscribers that can scale independently. Stage 3 subscriber scales based on GPS-cleaning load; Stage 5 subscriber scales based on Strava API latency.
- **Workflow orchestration:** Use a lightweight workflow engine (Cloud Workflows, or even a simple state machine in Firestore) to track stage completion and handle retries.
- **Async processing:** Move the Strava upload to a background task queue (Cloud Tasks) with a callback, freeing the subscriber to ACK the message and handle the next one.
- They should also note that the current design is fine for low throughput (< 100 activities/day) and the synchronous pattern is simpler to debug, but doesn't scale.
---

## Summary Assessment

| Dimension | Grade | Notes |
|-----------|-------|-------|
| **Architecture & Design** | **B+** | Clean two-service async architecture. Pub/Sub is appropriate for this workload. Application factory pattern is correct. |
| **Data Engineering Patterns** | **A-** | Streaming generators, GCS composition, Firestore idempotency, Dropbox cursor sync — all production-grade. |
| **Code Quality** | **C+** | Two critical bugs (Strava never called, template key mismatch). Excessive commented-out code. No tests. Well-structured otherwise. |
| **Security** | **B+** | Secret Manager, path validation, middleware, signed URLs — all strong. `APP_JSON_KEYS` in env var is the only concern. |
| **Observability** | **B** | Structured Cloud Logging with severity levels and filename/lineno. No alerting or dashboards configured. |
| **Testing** | **F** | Zero automated tests. High risk for a pipeline with 5+ external integrations. |
| **Documentation** | **A-** | Comprehensive READMEs for both services. Architecture diagrams. 12-stage IaC bootstrap. Good inline comments. |

**Overall Verdict:** This is a well-architected pipeline with several advanced GCP patterns (GCS composition, Firestore idempotency, streaming generators) that demonstrates genuine data engineering maturity. However, **the two critical bugs in the Strava upload and email template rendering mean core features are broken in production.** The complete absence of automated testing is a red flag for any production deployment. With testing added and the critical bugs fixed, this would be a solid senior-level data engineering portfolio project.
