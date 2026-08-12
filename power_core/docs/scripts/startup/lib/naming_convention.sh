#!/usr/bin/env bash

#╔═══════════════════════════════════════════════════════════════════════════╗
#║ Naming Convention Library - Google Cloud Style                          ║
#║ Pattern: {org}-{env}-{app}-{component}[-{hash}]                         ║
#╚══════════════════════════════════════════════════════════════════════════╝

# Generate a short hash suffix for global uniqueness (GCS buckets)
# Uses first 6 chars of SHA256 of the base identifier
generate_hash_suffix() {
    local base_string="$1"
    echo -n "${base_string}" | sha256sum | head -c 6
}

#╔═══════════════════════════════════════════════════════════════════════════╗
#║ Generate all resource names                                             ║
#╚══════════════════════════════════════════════════════════════════════════╝
# Usage: generate_all_names <org_prefix> <env> <app_name> <project_id_suffix>
# Returns: associative array NAMES with all generated resource names
generate_all_names() {
    local org_prefix="$1"
    local env="$2"
    local app_name="$3"
    local project_id_suffix="$4"

    # Validate inputs
    if [[ -z "${org_prefix}" || -z "${env}" || -z "${app_name}" ]]; then
        echo "ERROR: org_prefix, env, and app_name are required" >&2
        return 1
    fi

    # Normalize to lowercase and replace underscores with hyphens
    org_prefix=$(echo "${org_prefix}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
    env=$(echo "${env}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')
    app_name=$(echo "${app_name}" | tr '[:upper:]' '[:lower:]' | tr '_' '-')

    # Base identifier for hash generation
    local base_id="${org_prefix}-${env}-${app_name}"
    local hash_suffix
    hash_suffix=$(generate_hash_suffix "${base_id}")

    # Project ID (used as suffix for bucket uniqueness if not provided)
    local project_id="${base_id}"
    if [[ -n "${project_id_suffix}" ]]; then
        project_id="${project_id}-${project_id_suffix}"
    fi

    # Declare associative array for results
    declare -gA NAMES

    # --- Core Resources ---
    NAMES[project]="${base_id}"
    NAMES[project_id]="${project_id}"

    # --- Storage Buckets (with hash suffix for global uniqueness) ---
    NAMES[bucket_main]="${base_id}-main-${hash_suffix}"
    NAMES[bucket_output]="${base_id}-output-${hash_suffix}"
    NAMES[bucket_input]="${base_id}-input-${hash_suffix}"
    NAMES[bucket_build]="${base_id}-build-${hash_suffix}"

    # --- Service Accounts ---
    # GCP service account IDs are limited to 6-30 characters. The full
    # {org}-{env}-{app}-{purpose} pattern overflows that limit, so service
    # accounts use {org}-{env}-{purpose}. They are scoped per project
    # (which already encodes {org}-{env}-{app}), so no collision is possible.
    NAMES[sa_dropbox]="${org_prefix}-${env}-dropbox"
    NAMES[sa_strava]="${org_prefix}-${env}-strava"
    NAMES[sa_run]="${org_prefix}-${env}-run"

    # --- Secrets ---
    # Combined Dropbox + Strava credentials
    NAMES[secret_dropbox]="${base_id}-dropbox-secrets"
    # All other JSON key files (service account keys, etc.)
    NAMES[secret_fullstack_json_keys]="${base_id}-fullstack-app-json-keys"

    # --- Artifact Registry ---
    NAMES[artifact_registry]="${base_id}-docker"

    # --- Pub/Sub ---
    # Public pipeline topic (frontend user uploads -> Eventarc trigger)
    NAMES[pubsub_topic]="${base_id}-topic"
    NAMES[pubsub_dlq_topic]="${base_id}-topic-dlq"
    # Private pipeline topic (Dropbox sync -> push subscription)
    NAMES[pubsub_dropbox_topic]="${base_id}-dropbox-topic"
    NAMES[pubsub_dropbox_dlq_topic]="${base_id}-dropbox-topic-dlq"
    NAMES[pubsub_dropbox_subscription]="${base_id}-dropbox-sub"

    # --- Eventarc ---
    NAMES[eventarc_sa]="${org_prefix}-${env}-eventarc"
    NAMES[eventarc_trigger]="${base_id}-pubsub-trigger"

    # --- Cloud Run Services ---
    NAMES[cloud_run_core]="${base_id}-core"
    NAMES[cloud_run_pub]="${base_id}-site-handler"

    # --- Derived values for IAM ---
    NAMES[sa_dropbox_email]="${NAMES[sa_dropbox]}@${project_id}.iam.gserviceaccount.com"
    NAMES[sa_strava_email]="${NAMES[sa_strava]}@${project_id}.iam.gserviceaccount.com"
    NAMES[sa_run_email]="${NAMES[sa_run]}@${project_id}.iam.gserviceaccount.com"
    NAMES[sa_eventarc_email]="${NAMES[eventarc_sa]}@${project_id}.iam.gserviceaccount.com"
    NAMES[compute_sa]="${project_id}-compute@developer.gserviceaccount.com"
}

#╔═══════════════════════════════════════════════════════════════════════════╗
#║ Display all names in a formatted table                                  ║
#╚══════════════════════════════════════════════════════════════════════════╝
display_names_table() {
    local env="$1"

    echo "╔══════════════════════════════════════════════════════════════════════════╗"
    echo "║  RESOURCE NAMING PLAN (Environment: ${env})"
    echo "╠══════════════════════════════════════════════════════════════════════════╣"
    printf "║  %-30s │ %s\n" "Resource" "Generated Name"
    echo "╠══════════════════════════════════════════════════════════════════════════╣"

    local resources=(
        "project:GCP Project ID"
        "bucket_main:Main Storage Bucket"
        "bucket_output:Public Output Bucket"
        "bucket_input:Public Input Bucket"
        "bucket_build:Cloud Build Staging Bucket"
        "sa_dropbox:Dropbox Service Account"
        "sa_strava:Strava Service Account"
        "sa_run:Cloud Run Service Account"
        "eventarc_sa:Eventarc Service Account"
        "secret_dropbox:Dropbox & Strava Secret"
        "secret_fullstack_json_keys:Fullstack JSON Keys Secret"
        "artifact_registry:Artifact Registry Repo"
        "pubsub_topic:Public Pub/Sub Topic"
        "pubsub_dropbox_topic:Private Pub/Sub Topic"
        "pubsub_dropbox_subscription:Private Pub/Sub Subscription"
        "eventarc_trigger:Eventarc Trigger"
        "cloud_run_core:Cloud Run Service (power-core)"
        "cloud_run_pub:Cloud Run Service (site-handler)"
    )

    for item in "${resources[@]}"; do
        local key="${item%%:*}"
        local label="${item##*:}"
        local name="${NAMES[$key]:-NOT GENERATED}"
        printf "║  %-30s │ %s\n" "${label}" "${name}"
    done

    echo "╠══════════════════════════════════════════════════════════════════════════╣"
    printf "║  %-30s │ %s\n" "Project ID (for IAM)" "${NAMES[project_id]}"
    printf "║  %-30s │ %s\n" "Dropbox SA Email" "${NAMES[sa_dropbox_email]}"
    printf "║  %-30s │ %s\n" "Strava SA Email" "${NAMES[sa_strava_email]}"
    printf "║  %-30s │ %s\n" "Run SA Email" "${NAMES[sa_run_email]}"
    printf "║  %-30s │ %s\n" "Eventarc SA Email" "${NAMES[sa_eventarc_email]}"
    printf "║  %-30s │ %s\n" "Compute SA Email" "${NAMES[compute_sa]}"
    echo "╚══════════════════════════════════════════════════════════════════════════╝"
}

#╔═══════════════════════════════════════════════════════════════════════════╗
#║ Get org prefix from user (with validation)                              ║
#╚══════════════════════════════════════════════════════════════════════════╝
get_org_prefix_from_user() {
    local org_prefix=""

    while true; do
        if ! read -r -p "Enter organization prefix (3-20 lowercase letters/numbers/hyphens, e.g., bigbikedata): " org_prefix; then
            echo "ERROR: No input received (non-interactive or EOF). Aborting." >&2
            return 2
        fi

        # Convert to lowercase
        org_prefix=$(echo "${org_prefix}" | tr '[:upper:]' '[:lower:]')

        # Validate: 3-20 chars, only lowercase letters, numbers, hyphens
        if [[ "${#org_prefix}" -lt 3 || "${#org_prefix}" -gt 20 ]]; then
            echo "  Invalid length. Must be 3-20 characters." >&2
            continue
        fi

        if [[ ! "${org_prefix}" =~ ^[a-z0-9-]+$ ]]; then
            echo "  Invalid characters. Only lowercase letters (a-z), numbers (0-9), and hyphens (-) allowed." >&2
            continue
        fi

        if [[ "${org_prefix}" =~ ^- || "${org_prefix}" =~ -$ ]]; then
            echo "  Cannot start or end with hyphen." >&2
            continue
        fi

        echo "${org_prefix}"
        break
    done
}

#╔═══════════════════════════════════════════════════════════════════════════╗
#║ Single approval loop for all generated names                            ║
#╚══════════════════════════════════════════════════════════════════════════╝
approve_names() {
    local env="$1"

    # Auto-approve without prompting (non-interactive / CI / dry-run)
    if [[ "${AUTO_APPROVE:-false}" == "true" ]]; then
        display_names_table "${env}"
        echo ""
        echo "✅ Names auto-approved (--yes). Proceeding..."
        return 0
    fi

    while true; do
        display_names_table "${env}"

        echo ""
        if ! read -r -p "Approve all names above? [Y]es / [N]o (re-enter org prefix): " -n 1 choice; then
            echo ""
            echo "ERROR: No input received (non-interactive or EOF). Aborting." >&2
            echo "Re-run with --yes to auto-approve, or provide input on a terminal." >&2
            return 2
        fi
        echo ""
        if [[ -z "${choice}" ]]; then
            echo "ERROR: Empty input received. Aborting (type Y/N or re-run with --yes)." >&2
            return 2
        fi

        choice=$(echo "${choice}" | tr '[:lower:]' '[:upper:]')

        if [[ "${choice}" == "Y" ]]; then
            echo "✅ Names approved. Proceeding with provisioning..."
            return 0
        elif [[ "${choice}" == "N" ]]; then
            echo "🔁 Re-generating names with new org prefix..."
            return 1
        else
            echo "❌ Invalid input. Please enter Y or N."
        fi
    done
}

#╔═══════════════════════════════════════════════════════════════════════════╗
#║ Main entry point: generate and approve all names                        ║
#╚══════════════════════════════════════════════════════════════════════════╝
# Usage: run_naming_stage <env> <org_prefix_from_config> <app_name_from_config>
# Sets global NAMES array and exports individual variables for backward compatibility
run_naming_stage() {
    local env="$1"
    local config_org_prefix="$2"
    local config_app_name="$3"

    local org_prefix="${config_org_prefix}"
    local app_name="${config_app_name}"

    # If org_prefix not in config, prompt user
    if [[ -z "${org_prefix}" ]]; then
        echo "Organization prefix not found in configuration."
        org_prefix=$(get_org_prefix_from_user)
    fi

    # If app_name not in config, use default
    if [[ -z "${app_name}" ]]; then
        app_name="power-core"
    fi

    # Generate and approve names (loop until approved)
    while true; do
        # Generate project name first to use as potential suffix
        local temp_project_id="${org_prefix}-${env}-${app_name}"
        generate_all_names "${org_prefix}" "${env}" "${app_name}" ""

        local approve_rc=0
        approve_names "${env}" || approve_rc=$?
        if [[ ${approve_rc} -eq 0 ]]; then
            break
        elif [[ ${approve_rc} -eq 2 ]]; then
            echo "ERROR: Name approval aborted (no input / non-interactive)." >&2
            return 2
        fi

        # User rejected (N) - get new org prefix
        org_prefix=$(get_org_prefix_from_user) || return 2
    done

    # Export all names as individual variables for backward compatibility
    export_generated_names

    echo "✅ All resource names generated and exported."
}

#╔═══════════════════════════════════════════════════════════════════════════╗
#║ Export generated names as individual variables                           ║
#╚══════════════════════════════════════════════════════════════════════════╝
export_generated_names() {
    export GEN_NAME_PROJECT="${NAMES[project]}"
    export GEN_NAME_PROJECT_ID="${NAMES[project_id]}"
    export GEN_NAME_BUCKET="${NAMES[bucket_main]}"
    export GEN_NAME_PUB_OUTPUT_BUCKET="${NAMES[bucket_output]}"
    export GEN_NAME_PUB_INPUT_BUCKET="${NAMES[bucket_input]}"
    export GEN_NAME_BUILD_BUCKET="${NAMES[bucket_build]}"
    export SA_NAME_DROPBOX="${NAMES[sa_dropbox]}"
    export SA_NAME_STRAVA="${NAMES[sa_strava]}"
    export SA_NAME_RUN="${NAMES[sa_run]}"
    export SEC_DROPBOX="${NAMES[secret_dropbox]}"
    export SEC_FULLSTACK_JSON_KEYS="${NAMES[secret_fullstack_json_keys]}"
    export ARTIFACT_REGISTRY="${NAMES[artifact_registry]}"
    export GCP_TOPIC_NAME="${NAMES[pubsub_topic]}"
    export GCP_DLQ_TOPIC_NAME="${NAMES[pubsub_dlq_topic]}"
    export DROPBOX_TOPIC_NAME="${NAMES[pubsub_dropbox_topic]}"
    export DROPBOX_DLQ_TOPIC_NAME="${NAMES[pubsub_dropbox_dlq_topic]}"
    export DROPBOX_SUBSCRIPTION_NAME="${NAMES[pubsub_dropbox_subscription]}"
    export EVENTARC_SA="${NAMES[eventarc_sa]}"
    export EVENTARC_TRIGGER="${NAMES[eventarc_trigger]}"
    export CLOUD_RUN_SERVICE="${NAMES[cloud_run_core]}"
    export CLOUD_RUN_SERVICE_PUB="${NAMES[cloud_run_pub]}"
    export SA_EMAIL_1="${NAMES[sa_dropbox_email]}"
    export SA_EMAIL_2="${NAMES[sa_strava_email]}"
    export SA_EMAIL_3="${NAMES[sa_run_email]}"
    export SA_EMAIL_EVENTARC="${NAMES[sa_eventarc_email]}"
    export COMPUTE_ACCOUNT="${NAMES[compute_sa]}"
}

# Persist every deterministic name needed by deployment and runtime setup.
# Secrets themselves are stored in Secret Manager; only their names are saved here.
persist_generated_names() {
    local env_file="${1:-names.env}"

    append_env_value "GCP_PROJECT_ID=${NAMES[project_id]}" "$env_file"
    append_env_value "GCP_PROJECT_NUMBER=${GCP_PROJECT_NUMBER:-${PROJECT_NUMBER:-}}" "$env_file"
    append_env_value "GCP_BUCKET_NAME=${NAMES[bucket_main]}" "$env_file"
    append_env_value "GCS_PUB_OUTPUT_BUCKET=${NAMES[bucket_output]}" "$env_file"
    append_env_value "GCS_PUB_INPUT_BUCKET=${NAMES[bucket_input]}" "$env_file"
    append_env_value "GCS_BUILD_BUCKET=${NAMES[bucket_build]}" "$env_file"

    append_env_value "SA_NAME_DROPBOX=${NAMES[sa_dropbox]}" "$env_file"
    append_env_value "SA_NAME_STRAVA=${NAMES[sa_strava]}" "$env_file"
    append_env_value "SA_NAME_RUN=${NAMES[sa_run]}" "$env_file"
    append_env_value "SA_NAME_EVENTARC=${NAMES[eventarc_sa]}" "$env_file"
    append_env_value "SA_EMAIL_DROPBOX=${NAMES[sa_dropbox_email]}" "$env_file"
    append_env_value "SA_EMAIL_STRAVA=${NAMES[sa_strava_email]}" "$env_file"
    append_env_value "SA_EMAIL_RUN=${NAMES[sa_run_email]}" "$env_file"
    append_env_value "SA_EMAIL_EVENTARC=${NAMES[sa_eventarc_email]}" "$env_file"
    append_env_value "COMPUTE_ACCOUNT=${NAMES[compute_sa]}" "$env_file"

    append_env_value "SEC_DROPBOX=${NAMES[secret_dropbox]}" "$env_file"
    append_env_value "SEC_FULLSTACK_JSON_KEYS=${NAMES[secret_fullstack_json_keys]}" "$env_file"
    append_env_value "APP_JSON_KEYS=${NAMES[secret_fullstack_json_keys]}" "$env_file"
    append_env_value "ARTIFACT_REGISTRY=${NAMES[artifact_registry]}" "$env_file"

    append_env_value "GCP_TOPIC_NAME=${NAMES[pubsub_topic]}" "$env_file"
    append_env_value "GCP_DLQ_TOPIC_NAME=${NAMES[pubsub_dlq_topic]}" "$env_file"
    append_env_value "DROPBOX_TOPIC_NAME=${NAMES[pubsub_dropbox_topic]}" "$env_file"
    append_env_value "DROPBOX_DLQ_TOPIC_NAME=${NAMES[pubsub_dropbox_dlq_topic]}" "$env_file"
    append_env_value "DROPBOX_SUBSCRIPTION_NAME=${NAMES[pubsub_dropbox_subscription]}" "$env_file"

    append_env_value "EVENTARC_SA=${NAMES[eventarc_sa]}" "$env_file"
    append_env_value "EVENTARC_TRIGGER=${NAMES[eventarc_trigger]}" "$env_file"
    append_env_value "CLOUD_RUN_SERVICE=${NAMES[cloud_run_core]}" "$env_file"
    append_env_value "CLOUD_RUN_SERVICE_PUB=${NAMES[cloud_run_pub]}" "$env_file"

    if [[ -n "${SA_DEPLOYER_EMAIL:-}" ]]; then
        append_env_value "SA_DEPLOYER_EMAIL=${SA_DEPLOYER_EMAIL}" "$env_file"
    fi
}

#╔═══════════════════════════════════════════════════════════════════════════╗
#║ Generate and export names without prompting (deterministic).             ║
#║ Used on resume so skipped stages still have the generated variables.     ║
#╚══════════════════════════════════════════════════════════════════════════╝
generate_and_export_names() {
    local env="$1"
    local org_prefix="$2"
    local app_name="$3"
    generate_all_names "${org_prefix}" "${env}" "${app_name}" ""
    export_generated_names
}
