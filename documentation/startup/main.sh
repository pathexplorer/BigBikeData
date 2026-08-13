#!/usr/bin/env bash

# ============================================================================
# Main interactive setup orchestrator for BigBikeData / power_core
#
# This is the NEW top-level entry point that replaces the old bare `start.sh`
# workflow. It splits the setup into three guided phases:
#
#   Phase 1 (Step 1/3): External Services wizard
#       Interactive walkthrough of external_services_setup.md, collecting the
#       per-environment credentials (Dropbox, Strava, Brevo/SMTP, hosting,
#       ngrok). Stored ENCRYPTED in `.external_services.{env}.gpg`.
#       Ends with a summary table of all collected variables & keys.
#
#   Phase 2 (Step 2/3): Cloud bootstrap
#       Delegates to the existing `start.sh {env}`, which provisions the GCP
#       project, IAM, secrets, Pub/Sub, Artifact Registry, Firestore, etc.
#
#   Phase 3 (Step 3/3): Runtime configuration + Secret Manager upload
#       Runs `configure_runtime.sh {env} --apply` (Firestore + generated
#       app-json keys) and uploads the wizard-collected external credentials
#       into the `dropbox-secrets` and `fullstack-app-json-keys` secrets.
#
# Usage: ./main.sh [dev|prod] [--dry-run] [--no-wizard] [--yes]
#        ./main.sh dev --no-wizard --dry-run   # unattended / CI preview
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Argument parsing (mirrors start.sh) ---
ENV_MODE="prod"
DRY_RUN=false
SKIP_WIZARD=false
AUTO_YES=false

for arg in "$@"; do
    case "$arg" in
        prod|dev) ENV_MODE="$arg" ;;
        --dry-run|-n) DRY_RUN=true ;;
        --no-wizard) SKIP_WIZARD=true ;;
        --yes|-y) AUTO_YES=true ;;
        --help|-h)
            echo "Usage: $0 [dev|prod] [--dry-run] [--no-wizard] [--yes]"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument '$arg'" >&2
            echo "Usage: $0 [dev|prod] [--dry-run] [--no-wizard] [--yes]" >&2
            exit 1
            ;;
    esac
done

if [[ "$ENV_MODE" != "prod" && "$ENV_MODE" != "dev" ]]; then
    echo "ERROR: Invalid environment '$ENV_MODE'. Use 'prod' or 'dev'." >&2
    exit 1
fi

# Export for library functions (start.sh uses the same contract via DRY_RUN).
export ENV_MODE DRY_RUN

# --- Load libraries ---
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/utils.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/external_wizard.sh"

# --- Resolve keys.env / names.env locations (same scan order as start.sh) ---
ENV_FILE="${VIRTUAL_ENV:-}/../keys.env.${ENV_MODE}"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE="$(dirname "${VIRTUAL_ENV:-}")/keys.env.${ENV_MODE}"
fi
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE="$SCRIPT_DIR/../../power_core/keys.env.${ENV_MODE}"
fi
NAMES_ENV_FILE="$SCRIPT_DIR/names.env"

if [ -f "$ENV_FILE" ]; then
    echo "Loading ${ENV_MODE} environment variables from $ENV_FILE..." >&2
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
fi
if [ -f "$NAMES_ENV_FILE" ]; then
    echo "Loading previously recorded resource names from $NAMES_ENV_FILE..." >&2
    set -a
    # shellcheck disable=SC1091
    source "$NAMES_ENV_FILE"
    set +a
fi

if [ "$DRY_RUN" = true ]; then
    echo "🔍 DRY-RUN MODE: no GCP resources will be created or modified"
    echo "============================================================"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║     BigBikeData / power_core — full environment setup     ${ENV_MODE}"
echo "║     Phase 1: external services wizard"
echo "║     Phase 2: cloud bootstrap (start.sh)"
echo "║     Phase 3: runtime config + secrets upload"
echo "╚══════════════════════════════════════════════════════════════════╝"

# ============================================================================
# STEP 1/3 — External services wizard
# ============================================================================
if [ "$SKIP_WIZARD" = false ]; then
    wizard_install_signal_trap
    run_external_wizard
    save_wizard_state
    trap - INT TERM
    show_external_summary

    # Review/change step: re-enter any single value without re-running the wizard.
    echo ""
    if [ "$AUTO_YES" = true ]; then
        echo "  --yes: skipping review step."
    else
        while true; do
            if wizard_yes_no "  Are the external services set up correctly?" "y"; then
                break
            fi
            echo "  Let's fix the values:"
            wizard_review_loop
            show_external_summary
            save_wizard_state
        done
    fi

    echo ""
    if [ "$AUTO_YES" = true ]; then
        echo "  --yes: proceeding to cloud bootstrap."
    else
        if ! wizard_yes_no "  Proceed to cloud bootstrap?"; then
            echo "  Aborting. Fix the credentials and re-run ./main.sh ${ENV_MODE} —"
            echo "  previously entered values will be pre-filled from the encrypted state."
            exit 1
        fi
    fi
fi

# ============================================================================
# STEP 2/3 — Cloud bootstrap (existing start.sh)
# ============================================================================
echo ""
echo "  ▶ Phase 2: running cloud bootstrap ./start.sh ${ENV_MODE} ..."
START_ARGS=("$ENV_MODE")
if [ "$DRY_RUN" = true ]; then
    START_ARGS+=("--dry-run")
fi
if [ "$AUTO_YES" = true ]; then
    START_ARGS+=("--yes")
fi

if ! "$SCRIPT_DIR/start.sh" "${START_ARGS[@]}"; then
    echo ""
    echo "❌ Cloud bootstrap failed. See the error above."
    echo "   External-services values are already saved encrypted — re-run ./main.sh ${ENV_MODE} to continue."
    exit 1
fi

# Re-load names.env — start.sh may have recorded new resource names.
if [ -f "$NAMES_ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$NAMES_ENV_FILE"
    set +a
fi

# ============================================================================
# STEP 3/3 — Runtime configuration + Secret Manager upload
# ============================================================================
echo ""
echo "  ▶ Phase 3: writing runtime config (Firestore + generated app-json keys)"
CONFIGURE_ARGS=("$ENV_MODE")
if [ "$DRY_RUN" = true ]; then
    CONFIGURE_ARGS+=("--dry-run")
else
    CONFIGURE_ARGS+=("--apply")
fi
if ! "$SCRIPT_DIR/configure_runtime.sh" "${CONFIGURE_ARGS[@]}"; then
    echo ""
    echo "⚠️  configure_runtime.sh reported a problem (e.g. a missing required value"
    echo "   like FRONTEND_BASE_URL). Set it and re-run ./main.sh ${ENV_MODE}."
    exit 1
fi

# Upload wizard-collected external credentials into the two secrets.
# Requires GCP_PROJECT_ID + SEC_DROPBOX + SEC_FULLSTACK_JSON_KEYS (names.env).
if [ "$SKIP_WIZARD" = false ]; then
    upload_external_secrets
else
    echo ""
    echo "  Skipping secret upload (--no-wizard: no collected credentials to upload)."
fi

# ============================================================================
# Final summary + what remains manual
# ============================================================================
echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║   Setup complete for ${ENV_MODE} — remaining manual steps"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo "  1. Wire Pub/Sub to the real Cloud Run URL AFTER first deploy:"
echo "       cd documentation/startup && ./wire_pubsub.sh ${ENV_MODE}"
echo "  2. Configure the Dropbox webhook URI to the deployed service URL"
echo "     (see external_services_setup.md §1.4)."
echo "  3. Custom domain + DNS (if not using *..web.app): see §4, then set"
echo "     FRONTEND_BASE_URL / ALLOWED_DOMAINS before deploying the frontend."
echo "  4. Deploy the services (gcloud builds submit --config ...cloudbuild.yaml)."
if [ "$DRY_RUN" = true ]; then
    echo ""
    echo "  🔍 DRY-RUN finished — nothing was created or modified."
fi
echo ""