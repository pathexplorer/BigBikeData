#!/bin/bash
# =============================================================================
# wire_pubsub.sh — Post-deploy Pub/Sub wiring helper.
#
# The bootstrap script (start.sh) cannot create a Cloud Run push subscription
# or an Eventarc trigger because both need the Cloud Run service URL, which only
# exists AFTER the first deploy (power_core_run.sh). Run this script once after
# the first deploy to:
#   1. Point the private push subscription at the real Cloud Run URL
#   2. Grant the Eventarc SA roles/run.invoker on the Cloud Run service
#   3. Create the Eventarc trigger for the public topic
#
# Usage:
#   ./wire_pubsub.sh [dev|prod] [--dry-run|-n]
#
# The Cloud Run URL is auto-detected via `gcloud run services describe`, or can
# be overridden with CLOUD_RUN_URL.
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_MODE="${1:-dev}"
DRY_RUN=false
[[ "$2" == "--dry-run" || "$2" == "-n" ]] && DRY_RUN=true
export DRY_RUN

if [[ "$ENV_MODE" != "prod" && "$ENV_MODE" != "dev" ]]; then
    echo "🯀 ERROR: Invalid environment '$ENV_MODE'. Use 'dev' or 'prod'."
    exit 1
fi

# --- Load libraries (naming + utils) ---
for f in "$SCRIPT_DIR"/lib/utils.sh "$SCRIPT_DIR"/lib/naming_convention.sh; do
    # shellcheck disable=SC1090
    source "$f"
done

# --- Load keys.env for ORG_PREFIX / APP_NAME / GCP_PROJECT_ID ---
VENV_PATH="$SCRIPT_DIR/../../../.venv"
ENV_FILE="$VENV_PATH/../keys.env.${ENV_MODE}"
if [[ ! -f "$ENV_FILE" ]]; then
    ENV_FILE="$SCRIPT_DIR/../../../keys.env.${ENV_MODE}"
fi
if [[ ! -f "$ENV_FILE" ]]; then
    echo "🯀 ERROR: Environment file not found: $ENV_FILE"
    echo "Set ORG_PREFIX/APP_NAME/GCP_PROJECT_ID manually and re-run."
    exit 1
fi
echo "Loading ${ENV_MODE} variables from $ENV_FILE..."
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# --- Generate deterministic resource names ---
generate_and_export_names "${ENV_MODE}" "${ORG_PREFIX}" "${APP_NAME}"

# Also load names.env if present (GCP_PROJECT_NUMBER etc.)
NAMES_ENV_FILE="$SCRIPT_DIR/names.env"
if [[ -f "$NAMES_ENV_FILE" ]]; then
    echo "Loading recorded resource names from $NAMES_ENV_FILE..."
    set -a
    # shellcheck disable=SC1090
    source "$NAMES_ENV_FILE"
    set +a
fi

GCP_PROJECT_ID="${GCP_PROJECT_ID:-${GEN_NAME_PROJECT}}"
CLOUD_RUN_URL="${CLOUD_RUN_URL:-}"
REGION="${REGION:-us-central1}"

private_sub="${DROPBOX_SUBSCRIPTION_NAME}"
private_topic="${DROPBOX_TOPIC_NAME}"
public_topic="${GCP_TOPIC_NAME}"
eventarc_sa_email="${SA_EMAIL_EVENTARC}"

# --- Resolve the real Cloud Run URL if not overridden ---
if [[ -z "$CLOUD_RUN_URL" ]]; then
    echo "Auto-detecting Cloud Run URL for service '$CLOUD_RUN_SERVICE'..."
    CLOUD_RUN_URL=$(gcloud run services describe "$CLOUD_RUN_SERVICE" \
        --region="$REGION" --project="$GCP_PROJECT_ID" --format="value(status.url)")
    echo "Detected: $CLOUD_RUN_URL"
fi
private_push_endpoint="${CLOUD_RUN_URL}/private-processing-handler"

if [[ "${DRY_RUN:-false}" == "true" ]]; then
    echo "🔍 [DRY-RUN] Project: $GCP_PROJECT_ID"
    echo "🔍 [DRY-RUN] Private subscription: $private_sub -> $private_push_endpoint"
    echo "🔍 [DRY-RUN] Eventarc SA: $eventarc_sa_email (run.invoker on $CLOUD_RUN_SERVICE)"
    echo "🔍 [DRY-RUN] Eventarc trigger: $EVENTARC_TRIGGER (topic $public_topic -> $CLOUD_RUN_URL/pubsub-processing-handler)"
    exit 0
fi

# 1. Point the private push subscription at the real Cloud Run URL
echo "Updating private push subscription '$private_sub'..."
gcloud pubsub subscriptions update "$private_sub" \
    --push-endpoint="$private_push_endpoint"

# 2. Grant the Eventarc SA the ability to invoke the Cloud Run service
echo "Granting roles/run.invoker to $eventarc_sa_email on $CLOUD_RUN_SERVICE..."
gcloud run services add-iam-policy-binding "$CLOUD_RUN_SERVICE" \
    --member="serviceAccount:$eventarc_sa_email" \
    --role="roles/run.invoker" \
    --region="$REGION" \
    --project="$GCP_PROJECT_ID"

# 3. Create the Eventarc trigger for the public topic
if gcloud eventarc triggers describe "$EVENTARC_TRIGGER" --location="$REGION" \
    --project="$GCP_PROJECT_ID" &>/dev/null; then
    echo "Eventarc trigger '$EVENTARC_TRIGGER' already exists. Skipping."
else
    echo "Creating Eventarc trigger '$EVENTARC_TRIGGER'..."
    gcloud eventarc triggers create "$EVENTARC_TRIGGER" \
        --location="$REGION" \
        --destination-run-service="$CLOUD_RUN_SERVICE" \
        --destination-run-region="$REGION" \
        --destination-run-path="/pubsub-processing-handler" \
        --event-filters="type=google.cloud.pubsub.topic.v1.messagePublished" \
        --transport-topic="projects/$GCP_PROJECT_ID/topics/$public_topic" \
        --service-account="$eventarc_sa_email"
fi

echo "✅ Pub/Sub wiring complete."
echo "Now set EVENTARC_SA='${EVENTARC_SA}' and EVENTARC_TRIGGER='${EVENTARC_TRIGGER}'"
echo "inside the 'fullstack-app-json-keys' secret."
