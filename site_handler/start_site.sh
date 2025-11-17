#!/bin/bash
# Script to submit the build
# Construct the --substitutions argument
# Note the comma separation and the underscore prefix for the keys

SUBS="_REGION=${REGION},_PRIVATE_ACCESS_TOKEN=${PRIVATE_ACCESS_TOKEN},_PRIVATE_UPLOAD_TOKEN=${PRIVATE_UPLOAD_TOKEN},_CLOUD_RUN_SERVICE_PUB=${CLOUD_RUN_SERVICE_PUB},_GCP_PROJECT_ID=${GCP_PROJECT_ID},_GCS_PUB_INPUT_BUCKET=${GCS_PUB_INPUT_BUCKET},_GCS_PUB_OUTPUT_BUCKET=${GCS_PUB_OUTPUT_BUCKET},_YAML_IMAGE_PUB=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${ARTIFACT_REGISTRY}/${CLOUD_RUN_SERVICE_PUB},_S_ACCOUNT_RUN=${SA_NAME_RUN}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"

# Submit the build
gcloud builds submit . \
    --config=site.yaml \
    --substitutions="${SUBS}"
