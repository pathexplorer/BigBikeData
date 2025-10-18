#!/bin/bash

PROJECT_ID=$(gcloud config get-value project)

# Describe users
USER1="serviceAccount:my-service-account@${PROJECT_ID}.iam.gserviceaccount.com"
USER2="user:someone@gmail.com"

# Roles by user
ROLES_USER1=(
  roles/storage.objectAdmin
  roles/secretmanager.admin
  roles/pubsub.serviceAgent
  roles/pubsub.publisher
)

ROLES_USER2=(
  roles/artifactregistry.writer
  roles/monitoring.viewer
)

echo "Assigned roles in the project: $PROJECT_ID"
echo "────────────────────────────────────────────"

# Checking roles
assign_roles() {
  local MEMBER=$1
  shift
  local ROLES=("$@")

  echo "Processing: $MEMBER"

  for ROLE in "${ROLES[@]}"; do
    EXISTS=$(gcloud projects get-iam-policy "$PROJECT_ID" \
      --flatten="bindings[]" \
      --format="value(bindings.members)" \
      --filter="bindings.role:$ROLE" | grep -c "$MEMBER")

    if [[ $EXISTS -gt 0 ]]; then
      echo "$MEMBER already have $ROLE, passed"
    else
      echo "➡Adding $ROLE for $MEMBER ..."
      gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="$MEMBER" \
        --role="$ROLE" \
        --quiet
    fi
  done
  echo ""
}

# Use function for each users
assign_roles "$USER1" "${ROLES_USER1[@]}"
assign_roles "$USER2" "${ROLES_USER2[@]}"

echo "Ready:"
gcloud projects get-iam-policy "$PROJECT_ID" --format="table(bindings.role, bindings.members)"
