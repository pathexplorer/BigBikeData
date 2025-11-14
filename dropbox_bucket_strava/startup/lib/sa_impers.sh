#!/bin/bash

# --- Configuration ---
TARGET_SA_EMAIL="${SA_NAME_DROPBOX}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
TARGET_SA_EMAIL_ST="${SA_NAME_STRAVA}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
MEMBER_TO_CHECK="serviceAccount:${SA_NAME_RUN}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
IMPERSONATION_ROLE="roles/iam.serviceAccountUser"
# --- End Configuration ---

echo "Checking if ${MEMBER_TO_CHECK} is bound to ${IMPERSONATION_ROLE} on ${TARGET_SA_EMAIL}..."

# 1. Get the IAM policy as JSON.
# 2. Use jq to filter for the specific role binding and extract the members list.
# 3. Use grep to search for the specific member email in the extracted list.
gcloud iam service-accounts get-iam-policy "${TARGET_SA_EMAIL}" \
    --format=json | \
    jq -r --arg ROLE_NAME "$IMPERSONATION_ROLE" \
         '.bindings[] | select(.role == $ROLE_NAME) | .members[]' | \
    grep -q "^${MEMBER_TO_CHECK}$"

# Check the exit code ($?) of the grep command
if [ $? -eq 0 ]; then
    echo -e "✅ Binding EXISTS: ${MEMBER_TO_CHECK} is already an impersonator."
    echo "No action needed."
else
    echo -e "❌ Binding NOT FOUND: ${MEMBER_TO_CHECK} needs the role."
    # The command to bind the role goes here if the check fails:
     gcloud iam service-accounts add-iam-policy-binding "${TARGET_SA_EMAIL}" \
         --member="${MEMBER_TO_CHECK}" \
         --role="${IMPERSONATION_ROLE}" \
         --quiet
fi

echo "Checking if ${MEMBER_TO_CHECK} is bound to ${IMPERSONATION_ROLE} on ${TARGET_SA_EMAIL_ST}..."

# 1. Get the IAM policy as JSON.
# 2. Use jq to filter for the specific role binding and extract the members list.
# 3. Use grep to search for the specific member email in the extracted list.
gcloud iam service-accounts get-iam-policy "${TARGET_SA_EMAIL_ST}" \
    --format=json | \
    jq -r --arg ROLE_NAME "$IMPERSONATION_ROLE" \
         '.bindings[] | select(.role == $ROLE_NAME) | .members[]' | \
    grep -q "^${MEMBER_TO_CHECK}$"

# Check the exit code ($?) of the grep command
if [ $? -eq 0 ]; then
    echo -e "✅ Binding EXISTS: ${MEMBER_TO_CHECK} is already an impersonator."
    echo "No action needed."
else
    echo -e "❌ Binding NOT FOUND: ${MEMBER_TO_CHECK} needs the role."
    # The command to bind the role goes here if the check fails:
     gcloud iam service-accounts add-iam-policy-binding "${TARGET_SA_EMAIL_ST}" \
         --member="${MEMBER_TO_CHECK}" \
         --role="${IMPERSONATION_ROLE}" \
         --quiet
fi