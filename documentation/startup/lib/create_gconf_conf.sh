#!/bin/bash

create_configuration() {
  local name_config=$1
  local project_name=$2
  local project_region=$3
  echo "------------------------------------------------"
  echo "--- 0. Create configuration in Google CLI..."
  echo "------------------------------------------------"
  
  if [[ "${DRY_RUN:-false}" == "true" ]]; then
      echo "🔍 [DRY-RUN] Would create gcloud configuration: $name_config"
      echo "🔍 [DRY-RUN] Would set project: $project_name"
      echo "🔍 [DRY-RUN] Would set region: $project_region"
      echo "🔍 [DRY-RUN] Would run: gcloud auth login"
      echo "🔍 [DRY-RUN] Would run: gcloud auth application-default login"
      return 0
  fi
  
  echo "Now you must be login in your default browser in your google account, which use in Google Cloud"
  echo "Browser opens automatically, click at all necessary buttons. Also, it need sto do twice, dont worry"

  # Idempotent: if the configuration already exists, just activate it and skip
  # the interactive create/login steps (safe to re-run after a reset).
  if gcloud config configurations list --format="value(name)" 2>/dev/null | grep -qx "$name_config"; then
      echo "   Configuration '$name_config' already exists. Activating..."
      run_cmd gcloud config configurations activate "$name_config"
      run_cmd gcloud config set project "$project_name"
      run_cmd gcloud config set compute/region "$project_region"
      run_cmd gcloud auth application-default set-quota-project "$project_name"
      return 0
  fi

  echo "Press any key to continue..."
  read -r -n 1 -s
  run_cmd gcloud config configurations create "$name_config"
  run_cmd gcloud auth login
  run_cmd gcloud config set project "$project_name"
  run_cmd gcloud config set compute/region "$project_region"
  run_cmd gcloud auth application-default login
  # Align the ADC quota project with the active project to silence the
  # "active project does not match the quota project" warning.
  run_cmd gcloud auth application-default set-quota-project "$project_name"
}

