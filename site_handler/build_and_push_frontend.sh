#!/bin/bash
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



echo "Dynamically building substitutions for Cloud Build..."
# Read the .env file line by line, ignoring comments and empty lines,
# and build the substitution string automatically.
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


# Add special substitutions that may not be in the env file
SUBS+="_YAML_IMAGE_PUB=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY}/${CLOUD_RUN_SERVICE_PUB}:${FRONTEND_TAG}"
#SUBS+=",_S_ACCOUNT_RUN=${SA_NAME_RUN}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
#SUBS+=",_S_ACCOUNT_STRAVA=${SA_NAME_STRAVA}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
#SUBS+=",_S_ACCOUNT_DROPBOX=${SA_NAME_DROPBOX}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

# --- FIX: REMOVE TRAILING COMMA ---
# This is the standard Bash way to strip the last character from a variable
SUBS="${SUBS%,}"
echo "SUBS value (after comma removal): $SUBS"
# ----------------------------------
echo "Substitutions prepared."

# THIS 10 LINES IS ADDON FOR VARIANT 2
LOCAL_DEP_PATH="../../gcp_actions"
# 2. Check if it exists to prevent vague errors later
if [ ! -d "$LOCAL_DEP_PATH" ]; then
    echo "❌ Error: Could not find dependency at $LOCAL_DEP_PATH"
    exit 1
fi
echo "Copying local dependency '$LOCAL_DEP_PATH' while excluding Git metadata..."
# --- FIX IMPLEMENTED HERE: Use rsync to exclude .git and handle permissions ---
# 3. Create the destination folder
mkdir -p ./gcp_actions
# 4. Use rsync to recursively copy ('-a') and safely exclude ('--exclude') the problematic .git folder.
rsync -a --exclude='.git' "$LOCAL_DEP_PATH/" ./gcp_actions
# ----------------------

# --- FIX 4: CONVERT DEPLOYER SA EMAIL TO FULL RESOURCE URL ---
# Assumes SA_NAME_DEPLOYER is set in keys.env (e.g., SA_NAME_DEPLOYER="bike-ci-deployer")
# And GCP_PROJECT_ID is set in keys.env

DEPLOYER_SA_RESOURCE_URL="projects/${GCP_PROJECT_ID}/serviceAccounts/${SA_DEPLOYER_EMAIL}"
DEPLOYER_BUCKET_URL="gs://${GCS_BUILD_BUCKET}/source-staging"
DEPLOYER_BUCKET_LOG="gs://${GCS_BUILD_BUCKET}/logs"

echo "Using Deployer SA Resource URL: $DEPLOYER_SA_RESOURCE_URL"
# -------------------------------------------------------------------

# --- Submit the Build ---
# The --ignore-file flag is crucial to exclude .venv, etc.
gcloud builds submit . \
    --config=cloudbuild.yaml \
    --ignore-file=.dockerignore \
    --substitutions="${SUBS}" \
    --service-account="$DEPLOYER_SA_RESOURCE_URL" \
    --gcs-source-staging-dir="$DEPLOYER_BUCKET_URL" \
    --gcs-log-dir="$DEPLOYER_BUCKET_LOG"
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