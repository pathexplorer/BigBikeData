#!/bin/bash

setup_deployment_env() {
    local choice
    local verif_input

    # Prompt for T or P (Read 1 character)
    read -r -p "Press T to push Test images or P to release to production: " -n 1 choice
    echo "" # Add newline for clean output

    # Normalize input to uppercase
    choice=$(echo "$choice" | tr '[:lower:]' '[:upper:]')

    if [[ "$choice" == "T" ]]; then
        echo "✅ Selected: TEST Environment"
        # Set Global Variables for Test
        BACKEND_DEV_OR_PROD="${CLOUD_RUN_SERVICE_OMICRON}"
        BACKEND_DEV_OR_PROD_TAG="${BACKEND_TAG_OMICRON}"
        return 0

    elif [[ "$choice" == "P" ]]; then
        # Production Safety Check
        echo "⚠️  Selected: PRODUCTION Environment"

        # Removed '-n 1' so user can type the full word "YES"
        read -r -p "ATTENTION! Are you sure to deploy in PRODUCTION? Type >> YES << to confirm: " verif_input

        if [[ "$verif_input" == "YES" ]]; then
            echo "🚀 Production confirmed."
            # Set Global Variables for Prod
            BACKEND_DEV_OR_PROD="${CLOUD_RUN_SERVICE}"
            BACKEND_DEV_OR_PROD_TAG="${BACKEND_TAG}"
            return 0
        else
            echo "❌ Deployment Cancelled: verification failed." >&2
            return 1 # Return 1 for logical failure (safety abort)
        fi

    else
        echo "❌ Invalid Input: Please press T or P." >&2
        return 2 # Return 2 for invalid arguments
    fi
}