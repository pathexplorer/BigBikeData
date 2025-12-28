#!/bin/bash
assign_roles_to_run_service_acc() {
  local MEMBER=$1
  local TYPE=$2
  local LEVEL=$3
  local LEVEL_NAME=$4
  shift 4
  local ROLES=("$@")


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




  echo "   - Checking/Binding $MEMBER to $LEVEL_NAME with $ROLE"

  # Unpacking array for possibility use function as argument in other function
  for file in "${ROLES[@]}"; do
      echo "   Processing config file: $file"
  done

  echo "Processing roles for: $MEMBER"

  for ROLE in "${ROLES[@]}"; do
    MEMBER_WITH_TYPE="$TYPE:$MEMBER"
    # Use gcloud's internal filter to check existence directly
    EXISTS=$(gcloud "$LEVEL" get-iam-policy "$LEVEL_NAME" \
        --flatten="bindings[]" \
        --filter="bindings.role='$ROLE' AND bindings.members:'$MEMBER_WITH_TYPE'" \
        --format="value(bindings.role)" | wc -l) # wc -l counts the matching lines

    if [[ $EXISTS -gt 0 ]]; then
      echo "   🮱 $MEMBER already has $ROLE."
    else
      echo "   ➡ Adding $ROLE for $MEMBER ..."
      gcloud "$LEVEL" add-iam-policy-binding "$LEVEL_NAME" \
        --member="$MEMBER_WITH_TYPE" \
        --role="$ROLE" \
        --condition=None &>/dev/null
    fi
  done
  echo "--- Finished role processing for $MEMBER_WITH_TYPE ---"
}


