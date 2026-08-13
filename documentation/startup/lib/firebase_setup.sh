#!/bin/bash

setup_firebase() {
    local project_id="${1:?project_id is required}"
    local env_mode="${2:-default}"

    echo "[i] Checking Firebase / site hosting setup for project $project_id..."

    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "   [DRY-RUN] Would link Firebase Hosting to project $project_id"
        echo "   [DRY-RUN] Would write site_handler/.firebaserc (alias '$env_mode')"
        echo "   [DRY-RUN] Would verify the project is Firebase-enabled"
        return 0
    fi

    # BASH_SOURCE[0] is lib/firebase_setup.sh -> ../../../ lands at the repo root.
    local project_root
    project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
    local site_dir="$project_root/site_handler"
    local firebaserc="$site_dir/.firebaserc"

    if ! command -v firebase >/dev/null 2>&1; then
        echo "   ⚠️  'firebase' CLI not found — automatic hosting link skipped."
        echo "      Enable Firebase for the project in the Firebase console, then install"
        echo "      the CLI (npm i -g firebase-tools) and deploy via site_handler_run.sh."
        FIREBASE_SETUP_WARNINGS+=("Firebase CLI not installed — hosting link skipped (stage_13). Enable Firebase in the console.")
        return 0
    fi

    if [[ ! -d "$site_dir" ]]; then
        echo "   ⚠️  site_handler directory not found at $site_dir — .firebaserc not created."
        FIREBASE_SETUP_WARNINGS+=("site_handler not found at $site_dir — .firebaserc not created.")
        return 0
    fi

    if ! printf '{\n  "projects": {\n    "default": "%s"\n  }\n}\n' "$project_id" > "$firebaserc" 2>/dev/null; then
        echo "   🯀 ERROR: Could not write $firebaserc"
        FIREBASE_SETUP_WARNINGS+=("Could not write $firebaserc for project $project_id.")
        return 1
    fi
    echo "   ✓ Linked Firebase Hosting to project $project_id ($firebaserc)."

    local enabled
    enabled="$(firebase projects:list --non-interactive --json 2>/dev/null \
        | jq -r --arg p "$project_id" 'any(.projects[]?; .projectId == $p)')"
    if [[ "$enabled" == "true" ]]; then
        echo "   ✓ Project $project_id is Firebase-enabled."
    else
        echo "   ⚠️  Project $project_id is not listed as a Firebase project yet."
        echo "      Enable Firebase for it in the Firebase console, then deploy hosting"
        echo "      with site_handler_run.sh (rewrite target injected from CLOUD_RUN_SERVICE_PUB)."
        FIREBASE_SETUP_WARNINGS+=("Project $project_id is NOT Firebase-enabled — enable it in the Firebase console.")
    fi

    echo "      Custom domain + DNS is a manual step (§4.1/4.3 of"
    echo "      documentation/external_services_setup.md)."
    return 0
}