#!/usr/bin/env bash

# Welcome Phase - Interactive collection of required variables

show_welcome() {
    local env_mode="$1"
    
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════════╗"
    echo "║         BigBikeData / power_core - GCP Project Bootstrap               ║"
    echo "║                        Welcome to Setup!                                ║"
    echo "╚══════════════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "This script will provision a complete GCP project for the power_core application."
    echo "Environment: ${env_mode}"
    echo ""
    echo "You need to provide the following information:"
    echo ""
}

prompt_for_variable() {
    local var_name="$1"
    local description="$2"
    local default_value="$3"
    local is_secret="$4"
    local current_value="${!var_name}"
    
    if [[ -n "$current_value" ]]; then
        if [[ "$is_secret" == "true" ]]; then
            echo "  $var_name: ******** (already set)"
        else
            echo "  $var_name: $current_value (already set)"
        fi
        return 0
    fi
    
    local prompt_text="  $var_name ($description)"
    if [[ -n "$default_value" ]]; then
        prompt_text="$prompt_text [default: $default_value]"
    fi
    prompt_text="$prompt_text: "
    
    local input_value=""
    while [[ -z "$input_value" ]]; do
        if [[ "$is_secret" == "true" ]]; then
            read -r -s -p "$prompt_text" input_value
            echo ""
        else
            read -r -p "$prompt_text" input_value
        fi
        
        if [[ -z "$input_value" && -n "$default_value" ]]; then
            input_value="$default_value"
        fi
        
        if [[ -z "$input_value" ]]; then
            echo "  This field is required. Please enter a value."
        fi
    done
    
    export "$var_name=$input_value"
    return 0
}

collect_required_variables() {
    local env_mode="$1"
    
    echo "Please provide the following required configuration:"
    echo ""
    
    # REGION
    prompt_for_variable "REGION" "GCP region (e.g., us-central1, europe-west1)" "us-central1" "false"
    
    # MY_USER_ACCOUNT
    prompt_for_variable "MY_USER_ACCOUNT" "Your Google account email (used for IAM bindings)" "" "false"
    
    # GCONFIG_NAME
    prompt_for_variable "GCONFIG_NAME" "Name for gcloud configuration" "power-core-${env_mode}" "false"
    
    # ORG_PREFIX
    prompt_for_variable "ORG_PREFIX" "Organization prefix (3-20 chars, lowercase, numbers, hyphens)" "bigbikedata" "false"
    
    # APP_NAME
    prompt_for_variable "APP_NAME" "Application name (used in all resource names)" "power-core" "false"
    
    # SA_DEPLOYER_EMAIL
    prompt_for_variable "SA_DEPLOYER_EMAIL" "Deployer service account email" "" "false"
    
    echo ""
    echo "All required variables collected."
    echo ""
}

offer_save_to_env_file() {
    local env_mode="$1"
    local env_file="${2:-keys.env.${env_mode}}"
    
    read -r -p "Save these values to $env_file for future runs? [Y/n]: " -n 1 choice
    echo ""
    
    choice=$(echo "${choice}" | tr '[:lower:]' '[:upper:]')
    
    if [[ -z "$choice" || "$choice" == "Y" ]]; then
        save_variables_to_env_file "$env_file"
        echo "✅ Configuration saved to $env_file"
    else
        echo "Configuration not saved. You'll need to enter these values again next time."
    fi
}

save_variables_to_env_file() {
    local env_file="$1"
    local vars=("REGION" "MY_USER_ACCOUNT" "GCONFIG_NAME" "ORG_PREFIX" "APP_NAME" "SA_DEPLOYER_EMAIL")
    
    {
        echo "# BigBikeData / power_core - Environment Configuration"
        echo "# Generated on $(date)"
        echo "# Environment: ${ENV_MODE}"
        echo ""
        
        for var in "${vars[@]}"; do
            local value="${!var}"
            if [[ -n "$value" ]]; then
                echo "${var}=\"${value}\""
            fi
        done
    } > "$env_file"
    
    chmod 600 "$env_file"
}

run_welcome_phase() {
    local env_mode="$1"
    local env_file="${2:-keys.env.${env_mode}}"
    
    show_welcome "$env_mode"
    collect_required_variables "$env_mode"
    offer_save_to_env_file "$env_mode" "$env_file"
    
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════════╗"
    echo "║  Starting GCP provisioning for ${env_mode} environment...                ║"
    echo "╚══════════════════════════════════════════════════════════════════════════╝"
    echo ""
}