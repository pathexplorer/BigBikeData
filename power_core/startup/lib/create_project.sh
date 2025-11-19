#!/bin/bash

create_gcp_project() {
    local gcp_project="$1"
    billing_account=$(gcloud beta billing accounts list --format="value(ACCOUNT_ID)")
    echo "--- GCP Project creation ---"

    # --- 0a. Check for Existence ---
    # This check relies on the gcp_project being defined externally (e.g., in .env)
    
    if gcloud projects describe "$gcp_project" &>/dev/null; then
        echo "Project $gcp_project already exists. Proceeding with resource checks."
    else
        echo "Project $gcp_project not found. Attempting to create it..."
    
        # 1. Check if creation variables are set
        if [[ -z "$gcp_project" ]] || [[ -z "$billing_account" ]]; then
            echo "   🯀 ERROR: gcp_project and billing_account must be set to create the project."
            echo "   Please set these environment variables and re-run."
            exit 1
        fi
    
        # 2. Attempt Project Creation
        # Use --folder=$FOLDER_ID if applicable, otherwise omit it.
        if gcloud projects create "$gcp_project" \
            --name="$gcp_project" \
            --enable-cloud-apis \
            --no-user-output-enabled 2>&1; then
            echo "   🮱 Project $gcp_project created successfully."
        else
            echo "   🯀 ERROR: Project creation failed. Check permissions (roles/resourcemanager.projectCreator)."
            exit 1
        fi
    
        # 3. Link Billing Account (Essential step after creation)
        echo "   Linking Billing Account..."
        if gcloud beta billing projects link "$gcp_project" \
            --billing-account="$billing_account" \
            --no-user-output-enabled 2>/dev/null; then
            echo "   🮱 Billing account linked successfully."
        else
            echo "   🯀 WARNING: Failed to link billing account. Resources requiring billing will fail."
            # Do not exit here; proceed to see if subsequent commands fix it or fail gracefully.
        fi
    
        # 4. Activate the new project configuration context
        echo "   Activating new project context..."
        gcloud config set project "$gcp_project" 2>/dev/null

        wait_and_counting_sheep "20"
    fi
    echo "--- Project create successfully ---"
}
