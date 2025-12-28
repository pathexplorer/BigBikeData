#!/bin/bash
# Script to submit the build for the 'power_core' service.
set -e

VENV_PATH="../.venv"

# Check if the activation script exists
if [ -f "$VENV_PATH/bin/activate" ]; then
    echo "Activating virtual environment..."
    # 🛑 Sourcing the activate script loads the necessary environment variables
    #    including ENV_FILE and all variables from keys.env.
    source "$VENV_PATH/bin/activate"
    echo "Virtual environment activated."
else
    echo "ERROR: Virtual environment activation script not found." >&2
    # Use an exit code to indicate failure (as per best practice)
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ ERROR: Environment file not found at $ENV_FILE. Aborting script."
    exit 1
fi

echo "Loading environment variables from $ENV_FILE..."
set -a
source "$ENV_FILE"
set +a

# --- Branch-specific configuration ---
BRANCH_NAME=$(git rev-parse --abbrev-ref HEAD)
SERVICE_SUFFIX=""
if [ "$BRANCH_NAME" != "master" ]; then
    SERVICE_SUFFIX="-$BRANCH_NAME" # e.g., -testing
fi

TARGET_SERVICE_NAME="${CLOUD_RUN_SERVICE}${SERVICE_SUFFIX}"
IMAGE_TAG=$BRANCH_NAME

echo "Branch: $BRANCH_NAME"
echo "Target Service: $TARGET_SERVICE_NAME"
echo "Image Tag: $IMAGE_TAG"
# ------------------------------------

echo "Dynamically building substitutions for Cloud Build..."
# --- Dynamic Substitution String Creation ---
SUBS=""
while IFS= read -r line || [[ -n "$line" ]]; do
    # Trim leading/trailing whitespace
    trimmed_line=$(echo "$line" | xargs)
    # Skip comments and empty lines
    if [[ "$trimmed_line" =~ ^\s*# || -z "$trimmed_line" ]]; then
        continue
    fi

    # Extract the variable name (part before the '=')
    key="${trimmed_line%%=*}"

    # Get the value of the variable from the already-sourced environment
    value="${!key}"

    # Append to the substitution string in the format _KEY=VALUE,
    SUBS+="_${key}=${value},"
done < "$ENV_FILE"

# Add/overwrite special substitutions for the build
SUBS+="_CLOUD_RUN_SERVICE=${TARGET_SERVICE_NAME},"
SUBS+="_YAML_IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY}/${TARGET_SERVICE_NAME}:${IMAGE_TAG}"

echo "Substitutions prepared."
# THIS 10 LINES IS ADDON FOR VARIANT 2
LOCAL_DEP_PATH="../../gcp_actions"
# 2. Check if it exists to prevent vague errors later
if [ ! -d "$LOCAL_DEP_PATH" ]; then
    echo "❌ Error: Could not find dependency at $LOCAL_DEP_PATH"
    exit 1
fi
# 3. Copy it into the current directory so Cloud Build can see it
# Using '-L' (dereference) is safer if you use symlinks, but '-r' is standard.
cp -r "$LOCAL_DEP_PATH" ./gcp_actions
# ----------------------

# --- FIX 4: CONVERT DEPLOYER SA EMAIL TO FULL RESOURCE URL ---
# Assumes SA_NAME_DEPLOYER is set in keys.env (e.g., SA_NAME_DEPLOYER="bike-ci-deployer")
# And GCP_PROJECT_ID is set in keys.env

DEPLOYER_SA_RESOURCE_URL="projects/${GCP_PROJECT_ID}/serviceAccounts/${SA_DEPLOYER_EMAIL}"
DEPLOYER_BUCKET_URL="gs://${GCS_BUILD_BUCKET}/source-staging"
DEPLOYER_BUCKET_LOG="gs://${GCS_BUILD_BUCKET}/logs"

echo "Using Deployer SA Resource URL: $DEPLOYER_SA_RESOURCE_URL"
# -------------------------------------------------------------------


echo "Submitting build from $(pwd)..."
set +e
# --- Submit the Build ---
# The build context is the entire project root '.', which allows access to all services.
echo "Submitting build from the project root directory..."
gcloud builds submit . \
    --config=cloudbuild.yaml \
    --ignore-file=.dockerignore \
    --substitutions="${SUBS}" \
    --service-account="$DEPLOYER_SA_RESOURCE_URL" \
    --gcs-source-staging-dir="$DEPLOYER_BUCKET_URL"
#    --gcs-log-dir="$DEPLOYER_BUCKET_LOG"

echo "✅ Cloud Build submitted successfully."
BUILD_EXIT_CODE=$?

# --- CLEANUP STEP ---
echo "Cleaning up vendored dependencies..."
rm -rf ./gcp_actions
# --------------------

# Re-enable strict mode and exit with the build's status
set -e
if [ $BUILD_EXIT_CODE -ne 0 ]; then
    echo "❌ Cloud Build failed."
    exit $BUILD_EXIT_CODE
fi