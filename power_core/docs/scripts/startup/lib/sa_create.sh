#!/bin/bash
# Define the variables for clarity
# Define a function to handle the check and creation of a Service Account (SA)
check_and_create_sa() {
  local sa_name=$1      # The service account name (e.g., SA_NAME_1)
  local sa_email=$2     # The full service account email (e.g., SA_EMAIL_1)
  local display_name=$3 # The desired display name
  echo "------------------------------------------------"
  echo "4. Checking/Creating App Service Accounts: $sa_name"
  echo "------------------------------------------------"
  
  if [[ "${DRY_RUN:-false}" == "true" ]]; then
      echo "🔍 [DRY-RUN] Would check if service account $sa_name exists"
      echo "🔍 [DRY-RUN] Would create service account $sa_name with display name '$display_name'"
      return 0
  fi
  
  # Check if the Service Account already exists by describing it
  # We suppress all output with &>/dev/null, only checking the exit code
  if gcloud iam service-accounts describe "$sa_email" &>/dev/null; then
    echo "   Service Account $sa_name already exists. Skipping creation."
  else
    echo "   Service Account $sa_name not found. Creating..."

    # Create the Service Account
    if run_cmd gcloud iam service-accounts create "$sa_name" \
      --display-name="$display_name"; then
      echo "   🮱 Service Account $sa_name created successfully."
    else
      echo "   🯀 ERROR: Failed to create Service Account $sa_name. Exiting."
      exit 1 # Exit the script upon failure
    fi
  fi
  echo "🮱 All service account checks complete."
}

