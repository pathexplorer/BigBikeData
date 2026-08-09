#!/bin/bash

create_firestore() {
local region=$1
echo "[i] Checking for existing Firestore database..."

# The 'if' condition will be true if grep finds the string "Listed 0 items."
# gcloud prints this summary to stderr, so both streams must be piped to grep.
if gcloud firestore databases list 2>&1 | grep -q "Listed 0 items."; then
    # This is the "pass" block
    echo "✓ Check passed: No database found. Ready to create."

    # Example: You would put your 'create' command here
    gcloud firestore databases create --location="$region"

else
    # This block runs if the string is NOT found
    echo "✗ Check failed: A database may already exist, or an error occurred."
    echo "   (Script will not attempt to create a new one.)"
    exit 1
fi

echo "[i] Script finished."
}