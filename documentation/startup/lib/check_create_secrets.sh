#!/bin/bash
check_and_create_secret() {
  local secret_name=$1
  local secret_value=$2
  local secret_label=$3
  echo "------------------------------------------------"
  echo " 0. Checking/Creating secret $secret_name"
  echo "------------------------------------------------"
  
  if [[ "${DRY_RUN:-false}" == "true" ]]; then
      echo "🔍 [DRY-RUN] Would check if secret $secret_name exists"
      echo "🔍 [DRY-RUN] Would create secret $secret_name with label app=$secret_label"
      return 0
  fi
  
  # Check if the secret already exists (suppress output with &>/dev/null)
  if gcloud secrets describe "$secret_name" &>/dev/null; then
    echo "     Secret $secret_name already exists. Skipping creation."
  else
    echo "     Secret $secret_name not found. Creating..."

    # Create the secret with its first version
    if echo -n "$secret_value" | run_cmd gcloud secrets create "$secret_name" \
      --data-file=- \
      --labels=app="$secret_label"; then
      echo "     🮱 Secret $secret_name created successfully."
    else
      echo "     🯀 ERROR: Failed to create Secret $secret_name. Exiting."
      exit 1
    fi
  fi
  echo "🮱 Secret checks complete."
}
