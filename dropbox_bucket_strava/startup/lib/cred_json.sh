#!/bin/bash

# Arguments: sa_name, project, resolved_path
create_json_cred() {
  local sa_name=$1
  local project=$2
  local creds_dir="$3"
  # --- 1. Get the directory name from the full path ---
  # This line is critical and should be uncommented.
  #local creds_dir=$(dirname "$resolved_path")

  # --- 2. Create the directory recursively if it doesn't exist ---
  # This prevents the gcloud command from failing due to a missing directory.
  #mkdir -p "$creds_dir" 2>/dev/null

  if [[ "$creds_dir" == *"\$HOME"* ]]; then
    echo "ERROR: \$HOME was not expanded! Check your .env loading." >&2
    exit 1
  fi
  echo "🔑 1. Checking and creating JSON key for Service Account: $sa_name"

  # 3. Check if the key file already exists (Idempotency check)
  if [[ -f "$creds_dir" ]]; then
    echo "   File $creds_dir already exists. Skipping key creation."
    return 0
  fi

  # 4. Attempt creation, suppressing gcloud noise
  echo "$creds_dir"
  if gcloud iam service-accounts keys create "$creds_dir" \
    --iam-account="${sa_name}"; then

    # 5. Final check for success based on file size
    if [[ -s "$creds_dir" ]]; then
        echo "   🮱 JSON key successfully created at: $creds_dir"
        return 0
    else
        # This handles the gcloud bug (exit 0, but 0-byte file)
        echo "   🯀 ERROR: Key created but is 0 bytes (likely a residual error)." >&2
        rm -f "$creds_dir" # Clean up the empty file
        return 1
    fi
  else
    # This handles gcloud failure (e.g., IAM permission denied)
    echo "   🯀 ERROR: Key creation failed. (Check Service Account Key Admin role)" >&2
    return 1
  fi
}