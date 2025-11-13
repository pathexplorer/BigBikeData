#!/bin/bash

assign_roles_to_user() {
  local MEMBER=$1
  shift 1
  local ROLES=("$@")
  # Unpacking array for possibility use function as argument in other function
  for file in "${ROLES[@]}"; do
      echo "   Processing config file: $file"
  done


  echo "Binding project-level IAM policies for: $MEMBER"

  for ROLE in "${ROLES[@]}"; do

    # Use gcloud's internal filter to check existence directly
    # Note: We must prefix the member type here too for the check!
    MEMBER_WITH_TYPE="user:$MEMBER"

    EXISTS=$(gcloud projects get-iam-policy "$GEN_NAME_PROJECT" \
        --flatten="bindings[]" \
        --filter="bindings.role='$ROLE' AND bindings.members:'$MEMBER_WITH_TYPE'" \
        --format="value(bindings.role)" | wc -l)

    if [[ $EXISTS -gt 0 ]]; then
      echo "   🮱 $MEMBER already has $ROLE."
    else
      echo "   ➡ Adding $ROLE for $MEMBER ..."

      # The core binding operation, suppressed for clean output
      gcloud projects add-iam-policy-binding "$GEN_NAME_PROJECT" \
        --member="$MEMBER_WITH_TYPE" \
        --role="$ROLE" \
        --condition=None &>/dev/null

      if [ $? -eq 0 ]; then
        echo "   🮱 Role $ROLE successfully added."
      else
        echo "   🯀 ERROR adding $ROLE. Check gcloud output."
      fi
    fi
  done
  echo "--- Finished role processing for $MEMBER ---"
}

