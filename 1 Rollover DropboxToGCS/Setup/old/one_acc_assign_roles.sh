#!/bin/bash

PROJECT_ID=$(gcloud config get-value project)
SERVICE_ACCOUNT="my-service-account@${PROJECT_ID}.iam.gserviceaccount.com"

ROLES=(
  roles/storage.objectAdmin
  roles/secretmanager.admin
  roles/pubsub.serviceAgent
  roles/pubsub.publisher
)

echo "Assigned roles for $SERVICE_ACCOUNT in project $PROJECT_ID"
echo "────────────────────────────────────────────"

for ROLE in "${ROLES[@]}"; do
  # Cheking for existing roles
  EXISTS=$(gcloud projects get-iam-policy "$PROJECT_ID" \
    --flatten="bindings[]" \
    --format="value(bindings.members)" \
    --filter="bindings.role:$ROLE" | grep -c "serviceAccount:${SERVICE_ACCOUNT}")

  if [[ $EXISTS -gt 0 ]]; then
    echo "Role $ROLE already exist, passed"
  else
    echo "Adding $ROLE..."
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:${SERVICE_ACCOUNT}" \
      --role="$ROLE" \
      --quiet
  fi
done

echo "READY"
gcloud projects get-iam-policy "$PROJECT_ID" --format="table(bindings.role, bindings.members)"
