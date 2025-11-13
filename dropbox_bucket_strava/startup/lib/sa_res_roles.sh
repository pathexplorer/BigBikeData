#!/bin/bash

binding_resource_level() {
  # Assign arguments to local, descriptive variables for clarity
  local SA_EMAIL="$1"        # The full service account email
  local SECRET_NAME="$2"     # The name of the secret (e.g., dropbox-secrets)
  local SA_NAME="$3"         # The service account's friendly name
  local ROLE="roles/secretmanager.secretAccessor" # The role to assign

  echo "   - Checking/Binding $SA_NAME to $SECRET_NAME with $ROLE"

  # 1. Define the full member string for filtering
  local MEMBER_WITH_TYPE="serviceAccount:$SA_EMAIL"

  # 2. Check if the binding already exists
  #    - We get the policy, flatten the bindings, and filter by both ROLE and MEMBER
  #    - wc -l counts the lines that match the criteria
  EXISTS=$(gcloud secrets get-iam-policy "$SECRET_NAME" \
    --flatten="bindings[]" \
    --filter="bindings.role='$ROLE' AND bindings.members:'$MEMBER_WITH_TYPE'" \
    --format="value(bindings.role)" | wc -l)

  if [[ $EXISTS -gt 0 ]]; then
    echo "     🮱 Binding already exists: $SA_NAME has $ROLE on $SECRET_NAME."
  else
    echo "     ➡ Adding binding..."

    # 3. Add the policy binding (suppressing output for clean script runs)
    gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
      --member="$MEMBER_WITH_TYPE" \
      --role="$ROLE" \
      --condition=None &>/dev/null

    if [ $? -eq 0 ]; then
      echo "     🮱 Binding successfully added."
    else
      echo "     🯀 ERROR: Failed to add binding for $SA_NAME on $SECRET_NAME."
      return 1
    fi
  fi
}
