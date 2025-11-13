#!/bin/bash

check_and_create_bucket() {
  local bucket_name=$1
  local region=$2
  local gs_uri="gs://${bucket_name}"
  echo "------------------------------------------------"
  echo "--- Checking/Creating GCS Bucket"
  echo "------------------------------------------------"
  # 2. Idempotency Check
  echo "     Checking GCS Bucket: $bucket_name in $region"
  if gsutil ls -b "$gs_uri" &>/dev/null; then
    echo "     Bucket $bucket_name already exists. Skipping creation."
  else
    echo "     Bucket not found. Creating..."

    # Create the bucket
    if gsutil mb -l "$region" "$gs_uri"; then
      echo "     Bucket created successfully."
    else
      echo "     ERROR: Failed to create Bucket $bucket_name. Exiting."
      exit 1
    fi
  fi
}
