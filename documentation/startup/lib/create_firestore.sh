#!/bin/bash

create_firestore() {
local region=$1
echo "[i] Checking for existing Firestore database..."

if [[ "${DRY_RUN:-false}" == "true" ]]; then
    echo "🔍 [DRY-RUN] Would check for existing Firestore database"
    echo "🔍 [DRY-RUN] Would create Firestore database in region $region"
    return 0
fi

local existing
existing=$(gcloud firestore databases list --format="json" 2>/dev/null | jq -r '.[]?.name' 2>/dev/null)
if [[ -n "$existing" ]]; then
    echo "✓ All good — Firestore database already present: $existing"
    return 0
fi

if run_cmd gcloud firestore databases create --location="$region" --type=firestore-native; then
    echo "✓ Firestore database created in region $region."
else
    echo "✗ Failed to create Firestore database in region $region."
    exit 1
fi

echo "[i] Script finished."
}