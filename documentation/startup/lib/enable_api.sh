#!/bin/bash
enable_gcp_apis() {
    local PROJECT_ID=$1
    shift 1
    local APIS_TO_CHECK=("$@")
    # loop to process the array:
    for file in "${APIS_TO_CHECK[@]}"; do
        echo "      Processing config file: $file"
    done

    # If the first argument is empty or not a valid project ID, assume all remaining are APIs.
    if [[ -z "$PROJECT_ID" || ! "$PROJECT_ID" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]]; then
        APIS_TO_CHECK=("$@")
        PROJECT_FLAG=""
        echo "Using current active project configuration."
    else
        PROJECT_FLAG="--project $PROJECT_ID"
        echo "      Targeting project: $PROJECT_ID"
    fi

    if [ ${#APIS_TO_CHECK[@]} -eq 0 ]; then
        echo "Error: No APIs provided to check." >&2
        return 1
    fi

    # API Check and Enable Loop
    for API_SERVICE in "${APIS_TO_CHECK[@]}"; do
        echo -n "      Checking status for $API_SERVICE... "

        if [[ "${DRY_RUN:-false}" == "true" ]]; then
            echo "🔍 [DRY-RUN] Would check/enable $API_SERVICE"
            continue
        fi

        # Check if the API is already enabled.
        # Use --filter and --format to get a precise, non-changing status.
        # This is an efficient API call (list_enabled_requests quota is 10 QPS).
        local STATUS
        STATUS=$(gcloud services list $PROJECT_FLAG \
            --filter="NAME:($API_SERVICE)" \
            --format="value(STATE)" 2>/dev/null)

        if [[ "$STATUS" == "ENABLED" ]]; then
            echo "🮱 Already ENABLED. Skipping."
        else
            echo "🯀 DISABLED. Enabling now..."

            # The enable command is the "expensive" operation (mutate_requests quota is 2 QPS).
            # We use the --async flag to return immediately and not wait for the long-running operation,
            # which improves script stability and speed.
            if run_cmd gcloud services enable "$API_SERVICE" $PROJECT_FLAG --async --quiet; then
                echo "   -> Operation started successfully."
            else
                # Capture the failure if the command itself fails (e.g., permission denied)
                echo "   -> ERROR: Failed to start enable operation for $API_SERVICE." >&2
                # Decide if you want to exit or continue. Continuing is more stable.
            fi
        fi
    done

    # Wait until every requested API reports ENABLED before returning. Without
    # this, later stages can trigger gcloud's interactive
    # "API [x] not enabled. Would you like to enable and retry?" prompt
    # (e.g. when 'gcloud config set compute/region' validates the region).
    if [[ "${DRY_RUN:-false}" != "true" ]]; then
        wait_for_apis "$PROJECT_ID" "${APIS_TO_CHECK[@]}"
    fi
}

# Wait (poll) until all requested APIs report ENABLED state.
# Usage: wait_for_apis <project_id> <api1> <api2> ...
wait_for_apis() {
    local project_id="$1"
    shift 1
    local apis=("$@")
    local max_wait=600
    local waited=0

    echo "      Waiting for ${#apis[@]} API(s) to be fully enabled..."

    while (( waited < max_wait )); do
        local all_enabled=true
        for api in "${apis[@]}"; do
            local status
            status=$(gcloud services list --project "$project_id" \
                --filter="NAME:($api)" \
                --format="value(STATE)" 2>/dev/null)
            if [[ "$status" != "ENABLED" ]]; then
                all_enabled=false
                break
            fi
        done

        if $all_enabled; then
            echo "      All APIs enabled."
            return 0
        fi

        sleep 10
        waited=$((waited + 10))
    done

    echo "      WARNING: Timed out after ${max_wait}s waiting for APIs to enable." >&2
    return 1
}


