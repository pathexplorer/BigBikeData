#!/usr/bin/env bash

# Optional Cleanup Script
# Removes resources created by start.sh for a specific environment
# Usage: ./cleanup.sh [prod|dev] [--dry-run] [--yes]

set -euo pipefail

SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"

# --- Parse arguments ---
ENV_MODE="prod"
DRY_RUN=false
AUTO_APPROVE=false

for arg in "$@"; do
    case "$arg" in
        prod|dev)
            ENV_MODE="$arg"
            ;;
        --dry-run|-n)
            DRY_RUN=true
            ;;
        --yes|-y)
            AUTO_APPROVE=true
            ;;
        *)
            echo "Usage: $0 [prod|dev] [--dry-run|-n] [--yes|-y]"
            exit 1
            ;;
    esac
done

if [[ "$DRY_RUN" == "true" ]]; then
    echo "🔍 DRY-RUN MODE: No resources will be deleted"
    echo "============================================================"
fi

# --- Load environment ---
source "${SCRIPT_DIR}/lib/utils.sh"

ENV_FILE="$VIRTUAL_ENV/../keys.env.${ENV_MODE}"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE="$(dirname "$VIRTUAL_ENV")/keys.env.${ENV_MODE}"
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "🯀 ERROR: Environment file not found at $ENV_FILE"
    exit 1
fi

echo "Loading ${ENV_MODE} environment from $ENV_FILE..."
set -a
source "$ENV_FILE"
set +a

# Load generated names
NAMES_ENV_FILE="${SCRIPT_DIR}/names.env"
if [ -f "$NAMES_ENV_FILE" ]; then
    echo "Loading resource names from $NAMES_ENV_FILE..."
    set -a
    source "$NAMES_ENV_FILE"
    set +a
fi

# Regenerate names to ensure we have all variables
source "${SCRIPT_DIR}/lib/naming_convention.sh"
generate_and_export_names "${ENV_MODE}" "${ORG_PREFIX}" "${APP_NAME}"

# Derive deployer SA email (matches start.sh logic)
deployer_name="${SA_DEPLOYER_EMAIL%%@*}"
SA_DEPLOYER_NAME="${deployer_name}"
SA_DEPLOYER_EMAIL="${deployer_name}@${GEN_NAME_PROJECT}.iam.gserviceaccount.com"

# Compute account for binding removal
COMPUTE_ACCOUNT="${GCP_PROJECT_NUMBER:-}-compute@developer.gserviceaccount.com"

# Pub/Sub service agent
PUBSUB_SA="service-${GCP_PROJECT_NUMBER:-}@gcp-sa-pubsub.iam.gserviceaccount.com"

echo ""
echo "=== Resources to be deleted ==="
echo "Project: ${GEN_NAME_PROJECT}"
echo "Region: ${REGION}"
echo ""
echo "Service Accounts:"
echo "  - ${SA_EMAIL_1} (Dropbox)"
echo "  - ${SA_EMAIL_2} (Strava)"
echo "  - ${SA_EMAIL_3} (Run)"
echo "  - ${SA_EMAIL_EVENTARC} (Eventarc)"
echo "  - ${SA_DEPLOYER_EMAIL} (Deployer)"
echo ""
echo "Secrets:"
echo "  - ${SEC_DROPBOX}"
echo "  - ${SEC_FULLSTACK_JSON_KEYS}"
echo ""
echo "Buckets:"
echo "  - gs://${GEN_NAME_BUCKET}"
echo "  - gs://${GEN_NAME_PUB_OUTPUT_BUCKET}"
echo "  - gs://${GEN_NAME_PUB_INPUT_BUCKET}"
echo "  - gs://${GEN_NAME_BUILD_BUCKET}"
echo ""
echo "Pub/Sub:"
echo "  - Topic: ${GCP_TOPIC_NAME}"
echo "  - Topic: ${GCP_DLQ_TOPIC_NAME}"
echo "  - Topic: ${DROPBOX_TOPIC_NAME}"
echo "  - Topic: ${DROPBOX_DLQ_TOPIC_NAME}"
echo "  - Subscription: ${DROPBOX_SUBSCRIPTION_NAME}"
echo ""
echo "Artifact Registry:"
echo "  - Repository: ${ARTIFACT_REGISTRY} in ${REGION}"
echo ""
echo "Firestore Database: (in project ${GEN_NAME_PROJECT})"
echo ""

if [[ "$AUTO_APPROVE" != "true" ]]; then
    read -p "Confirm deletion of ALL above resources? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
fi

run_cmd() {
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "🔍 [DRY-RUN] $*"
    else
        eval "$@"
    fi
}

# --- Deletion Functions ---

delete_pubsub() {
    echo "=== Deleting Pub/Sub Resources ==="
    
    # Delete subscription first (must be before topics)
    if [[ -n "${DROPBOX_SUBSCRIPTION_NAME:-}" ]]; then
        run_cmd gcloud pubsub subscriptions delete "${DROPBOX_SUBSCRIPTION_NAME}" --quiet 2>/dev/null || true
    fi
    
    # Delete topics
    for topic in "${GCP_TOPIC_NAME:-}" "${GCP_DLQ_TOPIC_NAME:-}" "${DROPBOX_TOPIC_NAME:-}" "${DROPBOX_DLQ_TOPIC_NAME:-}"; do
        if [[ -n "$topic" ]]; then
            run_cmd gcloud pubsub topics delete "$topic" --quiet 2>/dev/null || true
        fi
    done
}

delete_eventarc_trigger() {
    echo "=== Deleting Eventarc Trigger ==="
    if [[ -n "${EVENTARC_TRIGGER:-}" ]]; then
        run_cmd gcloud eventarc triggers delete "${EVENTARC_TRIGGER}" --location="${REGION}" --quiet 2>/dev/null || true
    fi
}

delete_artifact_registry() {
    echo "=== Deleting Artifact Registry ==="
    if [[ -n "${ARTIFACT_REGISTRY:-}" ]]; then
        run_cmd gcloud artifacts repositories delete "${ARTIFACT_REGISTRY}" --location="${REGION}" --quiet 2>/dev/null || true
    fi
}

delete_buckets() {
    echo "=== Deleting GCS Buckets ==="
    for bucket in "${GEN_NAME_BUCKET:-}" "${GEN_NAME_PUB_OUTPUT_BUCKET:-}" "${GEN_NAME_PUB_INPUT_BUCKET:-}" "${GEN_NAME_BUILD_BUCKET:-}"; do
        if [[ -n "$bucket" ]]; then
            run_cmd gsutil -m rm -r "gs://${bucket}" 2>/dev/null || true
        fi
    done
}

delete_secrets() {
    echo "=== Deleting Secret Manager Secrets ==="
    for secret in "${SEC_DROPBOX:-}" "${SEC_FULLSTACK_JSON_KEYS:-}"; do
        if [[ -n "$secret" ]]; then
            run_cmd gcloud secrets delete "$secret" --quiet 2>/dev/null || true
        fi
    done
}

delete_service_accounts() {
    echo "=== Deleting Service Accounts ==="
    
    # Remove IAM bindings first
    if [[ -n "${SA_DEPLOYER_EMAIL:-}" && -n "${GEN_NAME_PROJECT:-}" ]]; then
        run_cmd gcloud projects remove-iam-policy-binding "${GEN_NAME_PROJECT}" \
            --member="serviceAccount:${SA_DEPLOYER_EMAIL}" \
            --role="roles/run.admin" --quiet 2>/dev/null || true
        run_cmd gcloud projects remove-iam-policy-binding "${GEN_NAME_PROJECT}" \
            --member="serviceAccount:${SA_DEPLOYER_EMAIL}" \
            --role="roles/artifactregistry.writer" --quiet 2>/dev/null || true
        run_cmd gcloud projects remove-iam-policy-binding "${GEN_NAME_PROJECT}" \
            --member="serviceAccount:${SA_DEPLOYER_EMAIL}" \
            --role="roles/storage.objectViewer" --quiet 2>/dev/null || true
        run_cmd gcloud projects remove-iam-policy-binding "${GEN_NAME_PROJECT}" \
            --member="serviceAccount:${SA_DEPLOYER_EMAIL}" \
            --role="roles/logging.logWriter" --quiet 2>/dev/null || true
    fi
    
    if [[ -n "${MY_USER_ACCOUNT:-}" && -n "${SA_DEPLOYER_EMAIL:-}" ]]; then
        run_cmd gcloud iam service-accounts remove-iam-policy-binding "${SA_DEPLOYER_EMAIL}" \
            --member="user:${MY_USER_ACCOUNT}" \
            --role="roles/iam.serviceAccountUser" --quiet 2>/dev/null || true
    fi
    
    # Delete SAs
    for sa in "${SA_EMAIL_1:-}" "${SA_EMAIL_2:-}" "${SA_EMAIL_3:-}" "${SA_EMAIL_EVENTARC:-}" "${SA_DEPLOYER_EMAIL:-}"; do
        if [[ -n "$sa" ]]; then
            run_cmd gcloud iam service-accounts delete "$sa" --quiet 2>/dev/null || true
        fi
    done
}

delete_firestore() {
    echo "=== Deleting Firestore Database ==="
    if [[ -n "${GEN_NAME_PROJECT:-}" ]]; then
        # Firestore deletion requires gcloud alpha and is irreversible
        run_cmd gcloud alpha firestore databases delete "(default)" --project="${GEN_NAME_PROJECT}" --quiet 2>/dev/null || true
    fi
}

delete_project() {
    echo "=== Deleting GCP Project ==="
    if [[ -n "${GEN_NAME_PROJECT:-}" ]]; then
        run_cmd gcloud projects delete "${GEN_NAME_PROJECT}" --quiet 2>/dev/null || true
    fi
}

delete_gcloud_config() {
    echo "=== Removing gcloud Configuration ==="
    if [[ -n "${GCONFIG_NAME:-}" ]]; then
        run_cmd gcloud config configurations delete "${GCONFIG_NAME}" --quiet 2>/dev/null || true
    fi
}

# --- Main Execution Order ---
# Reverse order of creation to handle dependencies

echo ""
echo "Starting cleanup for ${ENV_MODE} environment..."
echo ""

delete_eventarc_trigger
delete_pubsub
delete_artifact_registry
delete_buckets
delete_secrets
delete_service_accounts
delete_firestore

# Project deletion is last (and optional - comment out if you want to keep project)
# delete_project

# Config deletion is last
delete_gcloud_config

echo ""
if [[ "${DRY_RUN:-false}" == "true" ]]; then
    echo "🔍 DRY-RUN COMPLETE - No resources were actually deleted"
else
    echo "✅ Cleanup complete for ${ENV_MODE} environment"
    echo ""
    echo "Note: GCP Project '${GEN_NAME_PROJECT:-<unknown>}' was NOT deleted."
    echo "To delete the project entirely, run:"
    echo "  gcloud projects delete ${GEN_NAME_PROJECT:-<project-id>}"
fi