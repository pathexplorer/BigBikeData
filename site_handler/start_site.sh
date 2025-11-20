#!/bin/bash
# Script to submit the build.
# It dynamically creates Cloud Build substitutions from an environment file.

set -e # Stop the script if any command fails

# --- Define the Single Source of Truth for Environment Variables ---
# Assuming this script is run from the project root (BigBikeData/)
ENV_FILE="/home/stas/Dropbox/projects/BigBikeData/power_core/project_env/keys.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ ERROR: Environment file not found at $ENV_FILE. Aborting script."
    exit 1
fi

echo "Loading environment variables from $ENV_FILE..."
# Load the variables from the .env file into the current shell
set -a
source "$ENV_FILE"
set +a

echo "Dynamically building substitutions for Cloud Build..."
# --- Dynamic Substitution String Creation ---
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

echo "Substitutions prepared."

# --- Submit the Build ---
# The --ignore-file flag is crucial to exclude .venv, etc.
gcloud builds submit . \
    --config=site.yaml \
    --ignore-file=.dockerignore \
    --substitutions="${SUBS}"

echo "✅ Cloud Build submitted successfully."
