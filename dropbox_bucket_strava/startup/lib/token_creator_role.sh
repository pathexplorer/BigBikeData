#!/bin/bash

#!/bin/bash
#
# Module: iam_grant_module.sh (Strict Argument-Only)
# Description: Contains functions to manage IAM Service Account policy bindings.
#
# RULE: Functions in this module use ONLY the variables passed to them as arguments.
#

# Helper function to check and add the IAM binding
# Arguments: sa_email, user_account, role, project_id
check_and_add_binding() {
    local sa_email=$1
    local my_user_account=$2
    local role=$3
    local project_id=$4

    # Construct the member ID from the argument
    local member_type_and_id="user:$my_user_account"

    echo "--- Checking $sa_email ---"

    # 1. Get the current IAM policy in JSON format
    # Project ID is now provided via argument ($project_id)
    local policy_json=$(gcloud iam service-accounts get-iam-policy "$sa_email" \
        --project="$project_id" \
        --format=json 2>/dev/null)

    if [ $? -ne 0 ]; then
        echo "🯀 ERROR: Failed to retrieve IAM policy for $sa_email. Check permissions or project setting." >&2
        return 1
    fi

    # 2. Check if the binding already exists by searching the JSON output.
    # Role is provided via argument ($role)
    if echo "$policy_json" | grep -q "\"role\": \"$role\"" && \
       echo "$policy_json" | grep -q "\"$member_type_and_id\""; then

        echo "🮱 Role binding for '$member_type_and_id' on '$sa_email' already exists. Skipping grant."
        return 0
    fi

    # 3. If the binding doesn't exist, add it
    echo "🚀 Role binding not found. Granting $role to $my_user_account..."

    # Run the binding command, using all arguments provided to the function
    if gcloud iam service-accounts add-iam-policy-binding "$sa_email" \
        --member="$member_type_and_id" \
        --role="$role" \
        --project="$project_id"; then

        echo "🮱 Grant successful for $sa_email."
        return 0
    else
        echo "🯀 ERROR: Failed to grant role to $sa_email." >&2
        return 1
    fi
}

# Main function utilizing the helper to grant the Token Creator Role
# Arguments: sa_email1, sa_email2, user_account, role, project_id
grant_the_token_creator_role() {
  local sa_email1=$1
  local sa_email2=$2
  local my_user_account=$3
  local target_role=$4
  local gcp_project=$5

  echo "========================================"
  echo "Granting Token Creator Role to user: $my_user_account"
  echo "Project: $gcp_project, Role: $target_role"
  echo "========================================"

  local overall_status=0

  # Call helper, passing ALL required parameters down
  check_and_add_binding "$sa_email1" "$my_user_account" "$target_role" "$gcp_project"
  local status1=$?

  # Call helper for the second SA
  check_and_add_binding "$sa_email2" "$my_user_account" "$target_role" "$gcp_project"
  local status2=$?

  # Combine status: if either failed, the function returns 1
  if [ $status1 -ne 0 ] || [ $status2 -ne 0 ]; then
      return 1
  fi

  return 0
}

remove_the_token_creator_role() {
  local sa_email1=$1
  local sa_email2=$2
  local my_user_account=$3

  gcloud iam service-accounts remove-iam-policy-binding "$sa_email1" \
      --member="user:$my_user_account" \
      --role="roles/iam.serviceAccountTokenCreator"
  echo "Removed grant the Token Creator Role from $sa_email1"
  gcloud iam service-accounts remove-iam-policy-binding "$sa_email2" \
      --member="user:$my_user_account" \
      --role="roles/iam.serviceAccountTokenCreator"
  echo "Removed grant the Token Creator Role from $sa_email2"
}