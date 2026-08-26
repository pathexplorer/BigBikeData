#!/bin/bash

set -e # Stop the script if any command fails

# --- Parse arguments ---
ENV_MODE="prod"
RESET_MODE=false
DRY_RUN=false
SKIP_WELCOME=false
AUTO_APPROVE=false

# Parse all arguments
for arg in "$@"; do
    case "$arg" in
        prod|dev)
            ENV_MODE="$arg"
            ;;
        reset)
            RESET_MODE=true
            ;;
        --dry-run|-n)
            DRY_RUN=true
            ;;
        --no-welcome)
            SKIP_WELCOME=true
            ;;
        --yes|-y)
            AUTO_APPROVE=true
            ;;
        *)
            echo "🯀 ERROR: Unknown argument '$arg'"
            echo "Usage: $0 [prod|dev] [reset] [--dry-run|-n] [--no-welcome] [--yes|-y]"
            exit 1
            ;;
    esac
done

if [[ "$ENV_MODE" != "prod" && "$ENV_MODE" != "dev" ]]; then
    echo "🯀 ERROR: Invalid environment '$ENV_MODE'. Use 'prod' or 'dev'."
    echo "Usage: $0 [prod|dev] [reset] [--dry-run|-n]"
    exit 1
fi

# Export DRY_RUN for library functions
export DRY_RUN
# Export AUTO_APPROVE so naming functions can skip the interactive prompt
export AUTO_APPROVE

if [ "$DRY_RUN" = true ]; then
    echo "🔍 DRY-RUN MODE: No changes will be made to GCP resources"
    echo "============================================================"
fi

# --- Load core libraries first (needed for welcome phase) ---
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${ROOT_DIR}/lib/utils.sh"

# --- Load welcome phase library ---
source "${ROOT_DIR}/lib/welcome.sh"

# --- load environment file ---
# Use environment-specific keys.env file
# First try: parent of virtual env (for repo root)
# Second try: power_core directory (for power_core subdirectory)
ENV_FILE="$VIRTUAL_ENV/../keys.env.${ENV_MODE}"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE="$(dirname "$VIRTUAL_ENV")/keys.env.${ENV_MODE}"
fi
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE="$ROOT_DIR/../../power_core/keys.env.${ENV_MODE}"
fi

if [ -f "$ENV_FILE" ]; then
    echo "Loading ${ENV_MODE} environment variables from $ENV_FILE..."
    set -a
    source "$ENV_FILE"
    set +a
    
    # Check if all required vars are present, run welcome for any missing
    MISSING_VARS=()
    for var in "REGION" "MY_USER_ACCOUNT" "GCONFIG_NAME" "ORG_PREFIX" "APP_NAME" "SA_DEPLOYER_EMAIL"; do
        if [[ -z "${!var}" ]]; then
            MISSING_VARS+=("$var")
        fi
    done
    
    if [[ ${#MISSING_VARS[@]} -gt 0 && "$SKIP_WELCOME" == "false" ]]; then
        echo "Some required variables are missing from $ENV_FILE: ${MISSING_VARS[*]}"
        echo "Running welcome phase to collect missing configuration..."
        run_welcome_phase "$ENV_MODE" "$ENV_FILE"
    elif [[ ${#MISSING_VARS[@]} -gt 0 && "$SKIP_WELCOME" == "true" ]]; then
        echo "🯀 ERROR: Missing required variables: ${MISSING_VARS[*]}"
        echo "Run without --no-welcome to enter them interactively, or add them to $ENV_FILE"
        exit 1
    fi
else
    if [[ "$SKIP_WELCOME" == "true" ]]; then
        echo "🯀 ERROR: Environment file not found at $ENV_FILE and --no-welcome specified."
        echo "Create the file or run without --no-welcome to use interactive setup."
        exit 1
    fi
    echo "No environment file found at $ENV_FILE."
    echo "Running welcome phase to collect required configuration..."
    run_welcome_phase "$ENV_MODE" "$ENV_FILE"
fi

# Verify all required variables are set (welcome phase fills in any missing)
REQUIRED_VARS=(
"REGION"
"MY_USER_ACCOUNT"
"GCONFIG_NAME"
"ORG_PREFIX"
"APP_NAME"
"SA_DEPLOYER_EMAIL"
)
check_required_variables "${REQUIRED_VARS[@]}"

# gatekeeper1 start
STATE_FILE="script_progress_${ENV_MODE}.log"
export STATE_FILE
touch "$STATE_FILE"

# Handle a "reset" argument to clear the log
if [ "$RESET_MODE" = true ]; then
    echo "Resetting state file for ${ENV_MODE}..."
    > "$STATE_FILE"
fi
# gatekeeper1 end

# Export environment mode for use in library functions
export ENV_MODE

# --- Sourcing Modules (Libraries) ---
echo "Loading dependencies..."
load_variables_to_main() {
    local catalog=$1
    ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    LIB_DIR="${ROOT_DIR}/${catalog}"
    if [ -d "$LIB_DIR" ]; then
        echo "Loading library functions from $LIB_DIR..." >&2
        for script_file in "$LIB_DIR"/*.sh; do
            # Check if the file exists
            if [ -f "$script_file" ]; then
                # Source the script file, loading all functions and variables
                source "$script_file"
            fi
        done
    else
        echo "Error: ${catalog} directory not found at $LIB_DIR" >&2
        exit 1
    fi
}
load_variables_to_main "lib"
load_variables_to_main "addons"

# Stage warnings collected across the run (e.g. manual external steps) and
# re-printed in the final summary, so a "complete" script is never silent about
# warnings that appeared earlier.
FIREBASE_SETUP_WARNINGS=()

# ============================================================
# STAGE V: Pre-Flight Validation (NEW)
# ============================================================
stage_V_PREFLIGHT_VALIDATION() {
    echo "=== Running Pre-Flight Validation Checks ==="
    run_preflight_validation "${REGION}"
}
run_stage "stage_V_PREFLIGHT_VALIDATION"

# Load previously recorded resource values (names.env) so a resumed run still
# has GCP_PROJECT_ID/GCP_PROJECT_NUMBER etc. even when the earlier stages that
# record them (e.g. stage_3) are skipped by the progress log.
NAMES_ENV_FILE="$ROOT_DIR/names.env"
if [ -f "$NAMES_ENV_FILE" ]; then
    echo "Loading previously recorded resource names from $NAMES_ENV_FILE..."
    set -a
    source "$NAMES_ENV_FILE"
    set +a
    export PROJECT_NUMBER="${GCP_PROJECT_NUMBER:-$PROJECT_NUMBER}"
fi

# --- Configuration & Validation  ---
ROLES_SA_RUN=(
 roles/storage.objectAdmin
 roles/pubsub.serviceAgent
 roles/pubsub.publisher
 roles/secretmanager.admin
 roles/datastore.user
 roles/logging.logWriter # Added permission to write logs
)
ROLES_USER_ACCOUNT=(
 roles/artifactregistry.writer
)
ROLES_COMPUTE_ACCOUNT=(
 roles/run.admin
)
API_LIST=(
 secretmanager.googleapis.com
 compute.googleapis.com
 artifactregistry.googleapis.com
 firestore.googleapis.com
 cloudbuild.googleapis.com
 run.googleapis.com
 logging.googleapis.com # Added logging API
 pubsub.googleapis.com # Added Pub/Sub API
 eventarc.googleapis.com
 eventarcpublishing.googleapis.com
 iamcredentials.googleapis.com # API for impersonation
)
RESOURCE_SEC_ROLES=(
 roles/secretmanager.admin
)
IMPERSONATION_ROLES=(
roles/iam.serviceAccountUser
)
TEMP_ROLES=(
roles/iam.serviceAccountTokenCreator
)

REQUIRED_VARS=(
"REGION"
"MY_USER_ACCOUNT"
"GCONFIG_NAME"
"ORG_PREFIX"
"APP_NAME"
"SA_DEPLOYER_EMAIL"
)
check_required_variables "${REQUIRED_VARS[@]}"

# ============================================================
# STAGE 0: Generate and Approve All Resource Names (NEW)
# ============================================================
stage_0_GENERATE_NAMES() {
    echo "=== Generating All Resource Names ==="
    # run_naming_stage sets all GEN_NAME_*, SA_*, SEC_*, ARTIFACT_REGISTRY,
    # GCP_TOPIC_NAME, DROPBOX_TOPIC_NAME, CLOUD_RUN_SERVICE, etc.
    run_naming_stage "${ENV_MODE}" "${ORG_PREFIX}" "${APP_NAME}"
}
# Regenerate and export names deterministically BEFORE the gatekeeper stages.
# This guarantees skipped stages (e.g. on resume after a reset) still see the
# GEN_NAME_*, SA_*, SEC_* variables, which would otherwise be empty.
generate_and_export_names "${ENV_MODE}" "${ORG_PREFIX}" "${APP_NAME}"
persist_generated_names "$NAMES_ENV_FILE"
run_stage "stage_0_GENERATE_NAMES"

# Start timing the actual provisioning work. Stage 0's interactive name
# approval is a "user pause", so the timer begins after it.
timer_start

# The new naming convention already includes env in names (e.g., bigbikedata-dev-power-core)
# No need to append -dev suffix anymore - all names are pre-generated with correct env

stage_1_CREATE_PROJECT() {
      echo "=== Creating GCP Project ==="
      create_gcp_project "${GEN_NAME_PROJECT}"
      append_env_value "GCP_PROJECT_ID=${GEN_NAME_PROJECT}"
}
run_stage "stage_1_CREATE_PROJECT"

stage_2_ENABLE_ON_API() {
      # --- 3. Execution Sequence (Use functions from sourced files) ---
      run_with_retry \
          enable_gcp_apis \
          "${GEN_NAME_PROJECT}" \
          "${API_LIST[@]}"
}
run_stage "stage_2_ENABLE_ON_API"

stage_3_CONF_CREATE() {
      # Reusable universal method
      create_configuration "$GCONFIG_NAME" "$GEN_NAME_PROJECT" "$REGION"
      PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get-value project)" --format="value(projectNumber)")
      export GCP_PROJECT_NUMBER="${PROJECT_NUMBER}"
      append_env_value "GCP_PROJECT_NUMBER=${PROJECT_NUMBER}"
}
run_stage "stage_3_CONF_CREATE"

stage_4_BUCKET_SETUP() {
      # Reusable universal method - name pre-generated in Stage 0
      echo "=== Creating Main Bucket: ${GEN_NAME_BUCKET} ==="
      check_and_create_bucket "${GEN_NAME_BUCKET}" "${REGION}"
      append_env_value "GCP_BUCKET_NAME=${GEN_NAME_BUCKET}"
}
run_stage "stage_4_BUCKET_SETUP"

stage_4b_PUB_BUCKETS_SETUP() {
      # Create additional buckets for public pipeline (output and input) - names pre-generated in Stage 0
      echo "=== Creating Public Output Bucket: ${GEN_NAME_PUB_OUTPUT_BUCKET} ==="
      check_and_create_bucket "${GEN_NAME_PUB_OUTPUT_BUCKET}" "${REGION}"
      append_env_value "GCS_PUB_OUTPUT_BUCKET=${GEN_NAME_PUB_OUTPUT_BUCKET}"

      echo "=== Creating Public Input Bucket: ${GEN_NAME_PUB_INPUT_BUCKET} ==="
      check_and_create_bucket "${GEN_NAME_PUB_INPUT_BUCKET}" "${REGION}"
      append_env_value "GCS_PUB_INPUT_BUCKET=${GEN_NAME_PUB_INPUT_BUCKET}"
}
run_stage "stage_4b_PUB_BUCKETS_SETUP"

stage_4c_BUILD_BUCKET_SETUP() {
      # Create Cloud Build staging bucket - name pre-generated in Stage 0
      echo "=== Creating Cloud Build Staging Bucket: ${GEN_NAME_BUILD_BUCKET} ==="
      check_and_create_bucket "${GEN_NAME_BUILD_BUCKET}" "${REGION}"
      append_env_value "GCS_BUILD_BUCKET=${GEN_NAME_BUILD_BUCKET}"
}
run_stage "stage_4c_BUILD_BUCKET_SETUP"

stage_5_CREATE_SA() {
      check_and_create_sa "$SA_NAME_DROPBOX" "$SA_EMAIL_1" "Dropbox Service Account"
      check_and_create_sa "$SA_NAME_STRAVA" "$SA_EMAIL_2" "Strava Service Account"
      check_and_create_sa "$SA_NAME_RUN" "$SA_EMAIL_3" "Run Service Account"
}
run_stage "stage_5_CREATE_SA"

stage_5b_CREATE_DEPLOYER_SA() {
      echo "=== Creating CI/CD Deployer Service Account ==="
      # Derive the SA name from SA_DEPLOYER_EMAIL (prefix before @) and rebuild the
      # email against the CURRENT project, so an old-domain value in keys.env is corrected.
      local deployer_name="${SA_DEPLOYER_EMAIL%%@*}"
      SA_DEPLOYER_NAME="${deployer_name}"
      SA_DEPLOYER_EMAIL="${deployer_name}@${GEN_NAME_PROJECT}.iam.gserviceaccount.com"
      export SA_DEPLOYER_NAME SA_DEPLOYER_EMAIL

      check_and_create_sa "$SA_DEPLOYER_NAME" "$SA_DEPLOYER_EMAIL" "CI/CD Deployer and Admin"

      # Project-level roles (PART ONE)
      assign_roles_to_run_service_acc \
        "$SA_DEPLOYER_EMAIL" \
        "serviceAccount" \
        "projects" \
        "$GEN_NAME_PROJECT" \
        roles/run.admin \
        roles/artifactregistry.writer \
        roles/storage.objectViewer \
        roles/logging.logWriter

      # Allow the deployer to deploy as the Run service account
      assign_roles_to_run_service_acc \
        "$SA_DEPLOYER_EMAIL" \
        "serviceAccount" \
        "iam service-accounts" \
        "$SA_EMAIL_3" \
        roles/iam.serviceAccountUser

      # Build bucket access for source staging + logs
      assign_roles_to_run_service_acc \
        "$SA_DEPLOYER_EMAIL" \
        "serviceAccount" \
        "storage buckets" \
        "gs://${GEN_NAME_BUILD_BUCKET}" \
        roles/storage.objectAdmin \
        roles/storage.admin

      # PART TWO: allow the user account to submit builds as the deployer SA
      assign_roles_to_run_service_acc \
        "$MY_USER_ACCOUNT" \
        "user" \
        "iam service-accounts" \
        "$SA_DEPLOYER_EMAIL" \
        roles/iam.serviceAccountUser

      append_env_value "SA_DEPLOYER_EMAIL=${SA_DEPLOYER_EMAIL}"
}
run_stage "stage_5b_CREATE_DEPLOYER_SA"

stage_6_CREATE_SECRETS() {
    check_and_create_secret "$SEC_DROPBOX" "secret-data-for-app-1" "dropbox-strava"
    check_and_create_secret "$SEC_FULLSTACK_JSON_KEYS" "secret-data-for-app-3" "fullstack-json-keys"
}
run_stage "stage_6_CREATE_SECRETS"

stage_7_BIND_PROJ_ROLE_TO_SA() {
    COMPUTE_ACCOUNT="${GCP_PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
    # Setup main service account
    assign_roles_to_run_service_acc \
      "$SA_EMAIL_3" \
      "serviceAccount" \
      "projects" \
      "$GEN_NAME_PROJECT" \
      "${ROLES_SA_RUN[@]}"
    # for set --allow-unauthorization in step in Cloud Bild
    assign_roles_to_run_service_acc \
      "$COMPUTE_ACCOUNT" \
      "serviceAccount" \
      "projects" \
      "$GEN_NAME_PROJECT" \
      "${ROLES_COMPUTE_ACCOUNT[@]}"
    # For push dockerfiles to Artifact Registry from local machine (by user personality)
    assign_roles_to_run_service_acc \
      "$MY_USER_ACCOUNT" \
      "user" \
      "projects" \
      "$GEN_NAME_PROJECT" \
      "${ROLES_USER_ACCOUNT[@]}"
    # 1\2 Create possibility use certain service account for access to certain secret
    # Both Dropbox and Strava SAs access the combined dropbox secret
    assign_roles_to_run_service_acc \
      "$SA_EMAIL_1" \
      "serviceAccount" \
      "secrets" \
      "$SEC_DROPBOX" \
      "${RESOURCE_SEC_ROLES[@]}"
    assign_roles_to_run_service_acc \
      "$SA_EMAIL_2" \
      "serviceAccount" \
      "secrets" \
      "$SEC_DROPBOX" \
      "${RESOURCE_SEC_ROLES[@]}"
    # 2\2 Grant to service accounts to do form person main service account
    assign_roles_to_run_service_acc \
      "$SA_EMAIL_3" \
      "serviceAccount" \
      "iam service-accounts" \
      "$SA_EMAIL_1" \
      "${IMPERSONATION_ROLES[@]}"
    assign_roles_to_run_service_acc \
      "$SA_EMAIL_3" \
      "serviceAccount" \
      "iam service-accounts" \
      "$SA_EMAIL_2" \
      "${IMPERSONATION_ROLES[@]}"
    
    # Grant the main run SA the ability to impersonate ITSELF to sign URLs
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "🔍 [DRY-RUN] Would grant roles/iam.serviceAccountTokenCreator to ${SA_EMAIL_3} (self-impersonation)"
    else
        gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL_3" \
            --member="serviceAccount:$SA_EMAIL_3" \
            --role="roles/iam.serviceAccountTokenCreator"
    fi

    # template grant role to dropbox and strava
    assign_roles_to_run_service_acc \
      "$MY_USER_ACCOUNT" \
      "user" \
      "iam service-accounts" \
      "$SA_EMAIL_1" \
      "${TEMP_ROLES[@]}"
    assign_roles_to_run_service_acc \
      "$MY_USER_ACCOUNT" \
      "user" \
      "iam service-accounts" \
      "$SA_EMAIL_2" \
      "${TEMP_ROLES[@]}"
    # Wait 10 seconds for binding roles
    wait_and_counting_sheep "40"
    run_with_retry \
      sa_binding_verif \
      "$SA_NAME_DROPBOX" \
      "$SA_NAME_STRAVA" \
      "$SEC_DROPBOX" \
      "$SEC_FULLSTACK_JSON_KEYS" \
      "$SA_EMAIL_1" \
      "$SA_EMAIL_2"
    if [ $? -ne 0 ]; then exit 1; fi
    remove_the_token_creator_role \
      "$SA_EMAIL_1" \
      "$SA_EMAIL_2" \
      "$MY_USER_ACCOUNT"
}
run_stage "stage_7_BIND_PROJ_ROLE_TO_SA"

stage_8_PUBSUB_SETUP() {
    echo "=== Setting up Pub/Sub topics, subscriptions and Eventarc ==="
    local public_topic="${GCP_TOPIC_NAME}"
    local public_dlq_topic="${GCP_DLQ_TOPIC_NAME}"
    local private_topic="${DROPBOX_TOPIC_NAME}"
    local private_dlq_topic="${DROPBOX_DLQ_TOPIC_NAME}"
    local private_subscription="${DROPBOX_SUBSCRIPTION_NAME}"
    local push_endpoint="${PUBSUB_PRIVATE_PUSH_ENDPOINT:-https://placeholder.invalid/private-processing-handler}"
    local pubsub_sa="service-${GCP_PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"

    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "🔍 [DRY-RUN] Would create Eventarc SA: $EVENTARC_SA"
        echo "🔍 [DRY-RUN] Would create public topic: $public_topic + DLQ: $public_dlq_topic"
        echo "🔍 [DRY-RUN] Would create private topic: $private_topic + DLQ: $private_dlq_topic"
        echo "🔍 [DRY-RUN] Would create private push subscription: $private_subscription -> $push_endpoint with DLQ policy"
        echo "🔍 [DRY-RUN] Would grant Pub/Sub SA ($pubsub_sa): eventarc.eventReceiver + iam.serviceAccountTokenCreator"
        return 0
    fi

    # Create the Eventarc SA (used for the public pipeline trigger)
    check_and_create_sa "$EVENTARC_SA" "$SA_EMAIL_EVENTARC" "Eventarc Invoker Service Account"

    # Create topics (public + private) and their dead-letter topics
    for topic in "$public_topic" "$public_dlq_topic" "$private_topic" "$private_dlq_topic"; do
        if ! gcloud pubsub topics describe "$topic" &>/dev/null; then
            echo "Creating Pub/Sub topic: $topic"
            run_cmd gcloud pubsub topics create "$topic"
        else
            echo "Pub/Sub topic $topic already exists."
        fi
    done

    # Grant the Pub/Sub service agent permissions for Eventarc + identity tokens
    echo "Granting Pub/Sub service agent permissions..."
    run_cmd gcloud projects add-iam-policy-binding "$GEN_NAME_PROJECT" \
        --member="serviceAccount:$pubsub_sa" \
        --role="roles/eventarc.eventReceiver"
    run_cmd gcloud projects add-iam-policy-binding "$GEN_NAME_PROJECT" \
        --member="serviceAccount:$pubsub_sa" \
        --role="roles/iam.serviceAccountTokenCreator"

    # Create the private push subscription with DLQ policy (placeholder URL —
    # updated to the real Cloud Run URL after first deploy via wire_pubsub.sh)
    if ! gcloud pubsub subscriptions describe "$private_subscription" &>/dev/null; then
        echo "Creating private push subscription '$private_subscription' with DLQ policy..."
        run_cmd gcloud pubsub subscriptions create "$private_subscription" \
            --topic="$private_topic" \
            --dead-letter-topic="$private_dlq_topic" \
            --max-delivery-attempts=5 \
            --push-endpoint="$push_endpoint"
    else
        echo "Subscription $private_subscription already exists. Updating with DLQ policy..."
        run_cmd gcloud pubsub subscriptions update "$private_subscription" \
            --dead-letter-topic="$private_dlq_topic" \
            --max-delivery-attempts=5
    fi

    echo "✅ Pub/Sub setup complete."
}
run_stage "stage_8_PUBSUB_SETUP"

stage_9_CREATE_ART_REG_REPO() {
  # DEPENDENCY: INSTALLED DOCKER
      echo "▶ Running Artifact Registry Setup..."
      # Call the idempotent creation function
      check_and_create_artifact_repo \
        "$ARTIFACT_REGISTRY" \
        "$REGION" \
        "Connect to repository"

      echo "--- Docker Auth Configuration ---"
      # The command should be run silently as it is idempotent on configured machines.
      DOCKER_HOST="${REGION}-docker.pkg.dev"
      echo "   ➡ Configuring Docker authentication for $DOCKER_HOST"

      if [[ "${DRY_RUN:-false}" == "true" ]]; then
          echo "🔍 [DRY-RUN] Would configure Docker auth for $DOCKER_HOST"
      else
          # --quiet skips the interactive "Do you want to continue (Y/n)?" prompt
          # and just writes the credential helper entry to the Docker config.
          gcloud auth configure-docker "$DOCKER_HOST" --quiet

          if [ $? -eq 0 ]; then
            echo "   🮱 Docker configuration successful."
          else
            echo "   🯀 WARNING: Docker configuration failed. You may not be able to push images."
          fi
      fi
}
run_stage "stage_9_CREATE_ART_REG_REPO"

stage_11_JSON_CREATE() {
    if [[ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]]; then
        create_json_cred "$SA_EMAIL_3" "$GEN_NAME_PROJECT" "$GOOGLE_APPLICATION_CREDENTIALS"
    else
        echo "Skipping JSON credential creation (GOOGLE_APPLICATION_CREDENTIALS not set)"
        echo "Using gcloud OAuth for authentication"
    fi
}
run_stage "stage_11_JSON_CREATE"

stage_12_FIRESTORE_CREATE() {
    create_firestore "$REGION"
}
run_stage "stage_12_FIRESTORE_CREATE"

stage_13_FIREBASE_SETUP() {
    setup_firebase "$GCP_PROJECT_ID" "$ENV_MODE"
}
run_stage "stage_13_FIREBASE_SETUP"

echo "Setup is complete and correct."
if [[ ${#FIREBASE_SETUP_WARNINGS[@]} -gt 0 ]]; then
    echo ""
    echo "⚠️ Setup finished, but the following manual steps are still pending:"
    for warning in "${FIREBASE_SETUP_WARNINGS[@]}"; do
        echo "   - $warning"
    done
fi
timer_pause
echo "Total Execution Time (excluding user pauses): ${TIMER_TOTAL_SECONDS} seconds"

# read -p "Do you want to clean up (delete) these resources? (y/N) " -n 1 -r
# echo
# if [[ $REPLY =~ ^[Yy]$ ]]
# then
#   cleanup
# fi
