#!/usr/bin/env bash

# Validation / Pre-flight Checks Library
# Provides comprehensive pre-deployment validation for GCP bootstrap

validate_gcloud_auth() {
    echo "🔍 Validating gcloud authentication..."
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "   [DRY-RUN] Would verify gcloud auth status"
        return 0
    fi

    local active_account
    active_account=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1)
    if [[ -z "$active_account" ]]; then
        echo "🯀 ERROR: No active gcloud account. Run 'gcloud auth login' and 'gcloud auth application-default login'"
        return 1
    fi
    echo "   ✅ Active account: $active_account"

    if ! gcloud auth application-default print-access-token &>/dev/null; then
        echo "🯀 ERROR: Application Default Credentials not set. Run 'gcloud auth application-default login'"
        return 1
    fi
    echo "   ✅ Application Default Credentials configured"
    return 0
}

validate_gcloud_version() {
    echo "🔍 Validating gcloud version..."
    local min_version="450.0.0"
    local current_version
    current_version=$(gcloud version --format="value(Google Cloud SDK)" 2>/dev/null | head -1)
    if [[ -z "$current_version" ]]; then
        echo "   ⚠️  Could not determine gcloud version"
        return 0
    fi

    local min_major min_minor min_patch
    IFS='.' read -r min_major min_minor min_patch <<< "$min_version"
    local cur_major cur_minor cur_patch
    IFS='.' read -r cur_major cur_minor cur_patch <<< "$current_version"

    if (( cur_major < min_major || (cur_major == min_major && cur_minor < min_minor) || (cur_major == min_major && cur_minor == min_minor && cur_patch < min_patch) )); then
        echo "   ⚠️  gcloud version $current_version is older than recommended $min_version"
        echo "      Consider updating: gcloud components update"
    else
        echo "   ✅ gcloud version $current_version (>= $min_version)"
    fi
    return 0
}

validate_required_tools() {
    echo "🔍 Validating required tools..."
    local missing_tools=()
    local tools=("docker" "jq" "openssl" "sha256sum")

    for tool in "${tools[@]}"; do
        if ! command -v "$tool" &>/dev/null; then
            missing_tools+=("$tool")
        else
            echo "   ✅ $tool: $(command -v "$tool")"
        fi
    done

    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        echo "🯀 ERROR: Missing required tools: ${missing_tools[*]}"
        echo "   Install them via your package manager (apt, brew, etc.)"
        return 1
    fi
    return 0
}

validate_docker_running() {
    echo "🔍 Validating Docker daemon..."
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "   [DRY-RUN] Would verify Docker daemon is running"
        return 0
    fi

    if ! docker info &>/dev/null; then
        echo "🯀 ERROR: Docker daemon is not running or current user lacks permission"
        echo "   Start Docker service and ensure user is in 'docker' group"
        return 1
    fi
    echo "   ✅ Docker daemon is accessible"
    return 0
}

validate_billing_account() {
    echo "🔍 Validating billing account access..."
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "   [DRY-RUN] Would verify billing account access"
        return 0
    fi

    local billing_accounts
    billing_accounts=$(gcloud billing accounts list --filter="open:true" --format="value(name)" 2>/dev/null)
    if [[ -z "$billing_accounts" ]]; then
        echo "🯀 ERROR: No open billing accounts found. A billing account is required to create a GCP project."
        echo "   Visit https://console.cloud.google.com/billing to set up billing"
        return 1
    fi
    echo "   ✅ Billing account(s) available: $(echo "$billing_accounts" | wc -l)"
    return 0
}

validate_quota_limits() {
    echo "🔍 Validating quota limits for project creation..."
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "   [DRY-RUN] Would check quota limits"
        return 0
    fi

    local project_limit
    project_limit=$(gcloud compute project-info describe --format="value(quotas[metric=PROJECTS].limit)" 2>/dev/null || echo "unknown")
    local project_usage
    project_usage=$(gcloud compute project-info describe --format="value(quotas[metric=PROJECTS].usage)" 2>/dev/null || echo "unknown")

    if [[ "$project_limit" != "unknown" && "$project_usage" != "unknown" ]]; then
        local remaining=$((project_limit - project_usage))
        if (( remaining <= 0 )); then
            echo "🯀 ERROR: Project quota exhausted ($project_usage/$project_limit). Request quota increase."
            return 1
        fi
        echo "   ✅ Project quota: $project_usage/$project_limit used ($remaining remaining)"
    else
        echo "   ⚠️  Could not determine project quota (may need 'compute.projects.get' permission)"
    fi
    return 0
}

validate_organization_policy() {
    echo "🔍 Validating organization policies (if applicable)..."
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "   [DRY-RUN] Would check org policies"
        return 0
    fi

    local org_id
    org_id=$(gcloud organizations list --format="value(ID)" --limit=1 2>/dev/null)
    if [[ -n "$org_id" ]]; then
        echo "   ℹ️  Organization detected: $org_id"
        echo "      Note: Org policies may restrict project creation, service usage, or IAM bindings."
        echo "      If deployment fails, check Organization Policy constraints."
    else
        echo "   ℹ️  No organization detected (using no-org project creation)"
    fi
    return 0
}

validate_region_availability() {
    local region="$1"
    echo "🔍 Validating region '$region' availability..."
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "   [DRY-RUN] Would verify region availability"
        return 0
    fi

    if ! gcloud compute regions describe "$region" &>/dev/null; then
        echo "🯀 ERROR: Region '$region' not found or not accessible"
        echo "   Run 'gcloud compute regions list' to see available regions"
        return 1
    fi
    echo "   ✅ Region '$region' is available"
    return 0
}

validate_api_prerequisites() {
    echo "🔍 Validating prerequisite APIs for bootstrap..."
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "   [DRY-RUN] Would check prerequisite APIs"
        return 0
    fi

    local prereq_apis=(
        "cloudresourcemanager.googleapis.com"
        "serviceusage.googleapis.com"
        "iam.googleapis.com"
        "cloudbilling.googleapis.com"
    )

    local missing_apis=()
    for api in "${prereq_apis[@]}"; do
        if ! gcloud services list --enabled --filter="name:$api" --format="value(name)" | grep -q "$api"; then
            missing_apis+=("$api")
        fi
    done

    if [[ ${#missing_apis[@]} -gt 0 ]]; then
        echo "   ⚠️  Prerequisite APIs not enabled: ${missing_apis[*]}"
        echo "      These will be enabled during Stage 2, but enabling them now may speed up project creation."
    else
        echo "   ✅ All prerequisite APIs already enabled"
    fi
    return 0
}

validate_network_connectivity() {
    echo "🔍 Validating network connectivity to GCP..."
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "   [DRY-RUN] Would verify network connectivity"
        return 0
    fi

    if ! curl -s --max-time 5 "https://www.googleapis.com" >/dev/null; then
        echo "🯀 ERROR: Cannot reach Google APIs. Check network/firewall/proxy settings."
        return 1
    fi
    echo "   ✅ Network connectivity to Google APIs verified"
    return 0
}

run_preflight_validation() {
    local region="${1:-${REGION:-us-central1}}"
    local all_passed=true

    echo ""
    echo "=========================================="
    echo "🚀 PRE-FLIGHT VALIDATION CHECKS"
    echo "=========================================="

    validate_gcloud_version || all_passed=false
    validate_required_tools || all_passed=false
    validate_docker_running || all_passed=false
    validate_gcloud_auth || all_passed=false
    validate_network_connectivity || all_passed=false
    validate_billing_account || all_passed=false
    validate_organization_policy || all_passed=false
    validate_region_availability "$region" || all_passed=false
    validate_quota_limits || all_passed=false
    validate_api_prerequisites || all_passed=false

    echo ""
    if [[ "$all_passed" == "true" ]]; then
        echo "✅ All pre-flight checks PASSED"
        return 0
    else
        echo "🯀 PRE-FLIGHT CHECKS FAILED - Fix issues above before proceeding"
        return 1
    fi
}