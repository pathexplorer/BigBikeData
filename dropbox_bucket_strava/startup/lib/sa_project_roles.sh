#!/bin/bash
assign_roles_to_run_service_acc() {
  local MEMBER=$1
  local TYPE=$2
  shift 2
  local ROLES=("$@")

  # Unpacking array for possibility use function as argument in other function
  for file in "${ROLES[@]}"; do
      echo "   Processing config file: $file"
  done

  echo "Processing roles for: $MEMBER"

  for ROLE in "${ROLES[@]}"; do
    MEMBER_WITH_TYPE="$TYPE:$MEMBER"
    # Use gcloud's internal filter to check existence directly
    EXISTS=$(gcloud projects get-iam-policy "$GEN_NAME_PROJECT" \
        --flatten="bindings[]" \
        --filter="bindings.role='$ROLE' AND bindings.members:'$MEMBER_WITH_TYPE'" \
        --format="value(bindings.role)" | wc -l) # wc -l counts the matching lines

    if [[ $EXISTS -gt 0 ]]; then
      echo "   🮱 $MEMBER already has $ROLE."
    else
      echo "   ➡ Adding $ROLE for $MEMBER ..."
      gcloud projects add-iam-policy-binding "$GEN_NAME_PROJECT" \
        --member="$MEMBER_WITH_TYPE" \
        --role="$ROLE" \
        --condition=None &>/dev/null
    fi
  done
  echo "--- Finished role processing for $MEMBER_WITH_TYPE ---"
}


