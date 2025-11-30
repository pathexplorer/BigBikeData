#!/bin/bash
check_and_create_artifact_repo() {
  local REPO_NAME=$1
  local REPO_REGION=$2
  local DESCRIPTION=$3
  local REPO_FORMAT="docker" # Fixed for Docker format

  echo "5. Checking/Creating Artifact Registry Repository: $REPO_NAME"

  # 1. Check for existence (suppressing all output)
  if gcloud artifacts repositories describe "$REPO_NAME" \
    --location="$REPO_REGION"; then

    echo "   🮱 Repository $REPO_NAME already exists in $REPO_REGION. Skipping creation."
  else
    echo "   ➡ Repository $REPO_NAME not found. Creating..."

    # 2. Create the repository
    # We use --async for non-blocking creation, but we check the exit code immediately.
    if gcloud artifacts repositories create "$REPO_NAME" \
      --repository-format="$REPO_FORMAT" \
      --location="$REPO_REGION" \
      --description="$DESCRIPTION" \
      --immutable-tags \
      --async; then

      echo "   🮱 Repository $REPO_NAME creation initiated successfully (Async)."
      # NOTE: Using --async means the repository may not be ready immediately.
    else
      echo "   🯀 ERROR: Failed to create Repository $REPO_NAME. Exiting."
      exit 1
    fi
  fi
}