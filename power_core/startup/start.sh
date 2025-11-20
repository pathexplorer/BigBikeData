#!/bin/bash

set -e # Stop the script if any command fails
# --- load environment file ---
ENV_FILE="$VIRTUAL_ENV/../dropbox_bucket_strava/project_env/keys.env"
if [ -f "$ENV_FILE" ]; then
    echo "Loading project environment variables..."
    # 1. 'set -a' automatically exports all subsequent variables set or modified
    set -a
    # 2. 'source' (or '.') reads the file into the current shell.
    # Variables are loaded safely, handling spaces and special characters.
    source "$ENV_FILE"
    # 3. 'set +a' disables the automatic export feature
    set +a
else
    echo "🯀 ERROR: Environment file not found at $ENV_FILE. Aborting script."
    exit 1
fi

# gatekeeper1 start
STATE_FILE="script_progress.log"
export STATE_FILE
touch "$STATE_FILE"

# Handle a "reset" argument to clear the log
# Run: ./start.sh reset
if [ "$1" == "reset" ]; then
    echo "Resetting state file..."
    > "$STATE_FILE" # This clears the file
fi
# gatekeeper1 end

# --- Sourcing Modules (Libraries) ---
echo "Loading dependencies..."
load_variables_to_main() {
    local catalog=$1
    SCRIPT_DIR="$(dirname "${BASH_SOURCE[0]}")"
    LIB_DIR="${SCRIPT_DIR}/${catalog}"
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

# --- Configuration & Validation  ---
ROLES_SA_RUN=(
 roles/storage.objectAdmin
 roles/pubsub.serviceAgent
 roles/pubsub.publisher
 roles/secretmanager.admin
 roles/datastore.viewer
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
"GOOGLE_APPLICATION_CREDENTIALS"
"GCONFIG_NAME"
"SA_NAME_DROPBOX"
"SA_NAME_STRAVA"
"SA_NAME_RUN"
"SEC_DROPBOX"
"SEC_STRAVA"
"ARTIFACT_REGISTRY"
"GCP_TOPIC_NAME" # todo check after
"GCP_SUBSCRIPTION_NAME" # todo check after
)
check_required_variables "${REQUIRED_VARS[@]}"

stage_1_CREATE_PROJECT() {
      echo "=== Building GCP Project Name ==="
      project_prompts=("Org/App Prefix" "Descriptive Name")
      run_generation_loop \
          build_resource_name \
          "Project" \
          "9" \
          '${PREFIX_1}-${PREFIX_2}' \
          "${project_prompts[@]}"
      echo "✅ Script continued successfully after retry."
      timer_start
      GEN_NAME_PROJECT="$GENERATED_NAME"
      export GEN_NAME_PROJECT
      create_gcp_project "$GEN_NAME_PROJECT"
      echo "GCP_PROJECT_ID=${GEN_NAME_PROJECT}" >> names.env
}
timer_pause
run_stage "stage_1_CREATE_PROJECT"

SA_EMAIL_1="${SA_NAME_DROPBOX}@${GEN_NAME_PROJECT}.iam.gserviceaccount.com"
SA_EMAIL_2="${SA_NAME_STRAVA}@${GEN_NAME_PROJECT}.iam.gserviceaccount.com"
SA_EMAIL_3="${SA_NAME_RUN}@${GEN_NAME_PROJECT}.iam.gserviceaccount.com"

stage_2_ENABLE_ON_API() {
      # --- 3. Execution Sequence (Use functions from sourced files) ---
      run_with_retry \
          enable_gcp_apis \
          "$GEN_NAME_PROJECT" \
          "${API_LIST[@]}"
}
run_stage "stage_2_ENABLE_ON_API"

stage_3_CONF_CREATE() {
      # Reusable universal method
      create_configuration "$GCONFIG_NAME" "$GEN_NAME_PROJECT" "$REGION"
      PROJECT_NUMBER=$(gcloud projects describe "$(gcloud config get-value project)" --format="value(projectNumber)")
      echo "GCP_PROJECT_NUMBER=${PROJECT_NUMBER}" >> names.env
}
run_stage "stage_3_CONF_CREATE"

stage_4_BUCKET_SETUP() {
      # Reusable universal method
      echo "=== Building GCP Bucket Name ==="
      bucket_prompts=("Org/App Prefix" "Data Layer Descriptive" "Project or Team Descriptive")
      run_generation_loop \
          build_resource_name \
          "Bucket" \
          "18" \
          '${PREFIX_3}' \
          "${bucket_prompts[@]}"
      timer_start
      GEN_NAME_BUCKET="$GENERATED_NAME"
      export GEN_NAME_BUCKET
      echo "Exported name ${GEN_NAME_BUCKET}"
      check_and_create_bucket "$GEN_NAME_BUCKET" "$REGION"
      echo "GCP_BUCKET_NAME=${GEN_NAME_BUCKET}" >> names.env
}
timer_pause
run_stage "stage_4_BUCKET_SETUP"

stage_5_CREATE_SA() {
      check_and_create_sa "$SA_NAME_DROPBOX" "$SA_EMAIL_1" "Dropbox Service Account"
      check_and_create_sa "$SA_NAME_STRAVA" "$SA_EMAIL_2" "Strava Service Account"
      check_and_create_sa "$SA_NAME_RUN" "$SA_EMAIL_3" "Run Service Account"
}
run_stage "stage_5_CREATE_SA"

stage_6_BIND_PROJ_ROLE_TO_SA() {
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
      "$SEC_STRAVA" \
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
    gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL_3" \
        --member="serviceAccount:$SA_EMAIL_3" \
        --role="roles/iam.serviceAccountTokenCreator"

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
      "$SEC_STRAVA" \
      "$SA_EMAIL_1" \
      "$SA_EMAIL_2"
    if [ $? -ne 0 ]; then exit 1; fi
    remove_the_token_creator_role \
      "$SA_EMAIL_1" \
      "$SA_EMAIL_2" \
      "$MY_USER_ACCOUNT"
}
run_stage "stage_6_BIND_PROJ_ROLE_TO_SA"

stage_7_SECRETS() {
    check_and_create_secret "$SEC_DROPBOX" "secret-data-for-app-1" "dropbox"
    check_and_create_secret "$SEC_STRAVA" "secret-data-for-app-2" "strava"
}
run_stage "stage_7_SECRETS"

stage_8_PUBSUB_SETUP() {
    echo "=== Setting up Pub/Sub with Dead-Letter Queue ==="
    local main_topic="$GCP_TOPIC_NAME"
    local dlq_topic="${main_topic}-dlq"
    local subscription="$GCP_SUBSCRIPTION_NAME"

    # Create the main topic if it doesn't exist
    if ! gcloud pubsub topics describe "$main_topic" &>/dev/null; then
        echo "Creating main Pub/Sub topic: $main_topic"
        gcloud pubsub topics create "$main_topic"
    else
        echo "Main Pub/Sub topic $main_topic already exists."
    fi

    # Create the dead-letter topic if it doesn't exist
    if ! gcloud pubsub topics describe "$dlq_topic" &>/dev/null; then
        echo "Creating dead-letter topic: $dlq_topic"
        gcloud pubsub topics create "$dlq_topic"
    else
        echo "Dead-letter topic $dlq_topic already exists."
    fi

    # Create the main subscription with the dead-letter policy
    if ! gcloud pubsub subscriptions describe "$subscription" &>/dev/null; then
        echo "Creating subscription '$subscription' with DLQ policy..."
        gcloud pubsub subscriptions create "$subscription" \
            --topic="$main_topic" \
            --dead-letter-topic="$dlq_topic" \
            --max-delivery-attempts=5
    else
        echo "Subscription $subscription already exists. Updating with DLQ policy..."
        gcloud pubsub subscriptions update "$subscription" \
            --dead-letter-topic="$dlq_topic" \
            --max-delivery-attempts=5
    fi

    # Grant the Pub/Sub service account permission to publish to the DLQ topic
    local pubsub_sa="service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
    echo "Granting Pub/Sub service account permissions for DLQ..."
    gcloud pubsub topics add-iam-policy-binding "$dlq_topic" \
        --member="serviceAccount:$pubsub_sa" \
        --role="roles/pubsub.publisher"

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

      # The command should be run interactively to handle potential prompts,
      # but we suppress informational output for cleanliness.
      gcloud auth configure-docker "$DOCKER_HOST"

      if [ $? -eq 0 ]; then
        echo "   🮱 Docker configuration successful."
      else
        echo "   🯀 WARNING: Docker configuration failed. You may not be able to push images."
      fi
}
run_stage "stage_9_CREATE_ART_REG_REPO"

stage_11_JSON_CREATE() {
    create_json_cred "$SA_EMAIL_3" "$GEN_NAME_PROJECT" "$GOOGLE_APPLICATION_CREDENTIALS"
}
run_stage "stage_11_JSON_CREATE"

stage_12_FIRESTORE_CREATE() {
    create_firestore "$REGION"
}
run_stage "stage_12_FIRESTORE_CREATE"

echo "Setup is complete and correct."
timer_pause
echo "Total Execution Time (excluding user pauses): ${TIMER_TOTAL_SECONDS} seconds"

# read -p "Do you want to clean up (delete) these resources? (y/N) " -n 1 -r
# echo
# if [[ $REPLY =~ ^[Yy]$ ]]
# then
#   cleanup
# fi
