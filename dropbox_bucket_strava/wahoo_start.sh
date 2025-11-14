#!/bin/bash
# Script to submit the build
# Construct the --substitutions argument
# Note the comma separation and the underscore prefix for the keys

SUBS="_REGION=${REGION},_CLOUD_RUN_SERVICE=${CLOUD_RUN_SERVICE},_GCP_PROJECT_ID=${GCP_PROJECT_ID},_GCS_BUCKET_NAME=${GCS_BUCKET_NAME},_YAML_IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY}/${CLOUD_RUN_SERVICE},_S_ACCOUNT_RUN=${SA_NAME_RUN}@${GCP_PROJECT_ID}.iam.gserviceaccount.com,_S_ACCOUNT_STRAVA=${SA_NAME_STRAVA}@${GCP_PROJECT_ID}.iam.gserviceaccount.com,_S_ACCOUNT_DROPBOX=${SA_NAME_DROPBOX}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

# Submit the build
gcloud builds submit . \
    --config=wahoo.yaml \
    --substitutions="${SUBS}"
