#!/bin/bash

create_configuration() {
  local name_config=$1
  local project_name=$2
  local project_region=$3
  echo "------------------------------------------------"
  echo "--- 0. Create configuration in Google CLI..."
  echo "------------------------------------------------"
  echo "Now you must be login in your default browser in your google account, which use in Google Cloud"
  echo "Browser opens automatically, click at all necessary buttons. Also, it need sto do twice, dont worry"
  echo "Press any key to continue..."
  read -r -n 1 -s
  gcloud config configurations create "$name_config"
  gcloud auth login
  gcloud config set project "$project_name"
  gcloud config set compute/region "$project_region"
  gcloud auth application-default login
}

