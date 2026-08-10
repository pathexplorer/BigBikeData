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
  echo "Press any key to continue..."
  read -r -n 1 -s
  run_cmd gcloud config configurations create "$name_config"
  run_cmd gcloud auth login
  run_cmd gcloud config set project "$project_name"
  run_cmd gcloud config set compute/region "$project_region"
  run_cmd gcloud auth application-default login
}

