#!/bin/bash

# Function to verify two service accounts have access only to their designated secret.
# Arguments: sa_name_dropbox, sa_name_strava, sec_dropbox, sec_strava, sa_email_1, sa_email_2
sa_binding_verif() {
    local sa_name_dropbox="$1"
    local sa_name_strava="$2"
    local sec_dropbox="$3"
    local sec_strava="$4"
    local sa_email_1="$5"
    local sa_email_2="$6"
    local overall_status=0 # 0 means all tests passed

    echo "4. Verifying security access bindings..."

    # --- Helper function to display detailed failure message ---
    # $1: SA Name, $2: Secret Name, $3: Error Message
    handle_failure() {
        echo "       [❌ FAIL] $1 TEST FAILED: $2" >&2
        echo "       Reason: $3" >&2
        overall_status=1 # Set failure flag
    }

    # --- Test Group 1: SA 1 (dropbox-manager) ---
    echo "   Testing permissions for $sa_name_dropbox ($sa_email_1)..."

    # Test 1A: Should SUCCEED (Access is required)
    # The output (secret value) is captured to stdout/stderr is suppressed.
    local value_1A
    value_1A=$(gcloud secrets versions access latest --secret="$sec_dropbox" \
        --impersonate-service-account="$sa_email_1" 2>&1)

    if [ $? -eq 0 ]; then
        echo "     - Accessing $sec_dropbox (REQUIRED): ✅ Success. Value captured."
        # The secret value is now in $value_1A, ready for use if needed.
    else
        # SECURITY ERROR: SA 1 failed to access its OWN secret.
        handle_failure "$sa_name_dropbox" "Required access to $sec_dropbox was DENIED." "$value_1A"
    fi


    # Test 1B: Should BE DENIED (Access is forbidden)
    echo "     - Accessing $sec_strava (FORBIDDEN):"

    gcloud secrets versions access latest --secret="$sec_strava" \
        --impersonate-service-account="$sa_email_1" 2>/dev/null

    if [ $? -ne 0 ]; then
        # SUCCESS: Command returned non-zero (DENIED). This is the expected outcome.
        echo "       ✅ Success. Access was correctly denied."
    else
        # SECURITY VIOLATION: Command returned 0 (GRANTED).
        local violation_output=$(gcloud secrets versions access latest --secret="$sec_strava" --impersonate-service-account="$sa_email_1")
        handle_failure "$sa_name_dropbox" "Forbidden access to $sec_strava was GRANTED." "Value: $violation_output"
    fi


    # --- Test Group 2: SA 2 (strava-manager) ---
    echo "   Testing permissions for $sa_name_strava ($sa_email_2)..."

    # Test 2A: Should BE DENIED (Access is forbidden)
    echo "     - Accessing $sec_dropbox (FORBIDDEN):"

    gcloud secrets versions access latest --secret="$sec_dropbox" \
        --impersonate-service-account="$sa_email_2" 2>/dev/null

    if [ $? -ne 0 ]; then
        # SUCCESS: Command returned non-zero (DENIED). This is the expected outcome.
        echo "       ✅ Success. Access was correctly denied."
    else
        # SECURITY VIOLATION: Command returned 0 (GRANTED).
        handle_failure "$sa_name_strava" "Forbidden access to $sec_dropbox was GRANTED." "Check permissions on $sec_dropbox."
    fi


    # Test 2B: Should SUCCEED (Access is required)
    echo "     - Accessing $sec_strava (REQUIRED):"

    local value_2B
    value_2B=$(gcloud secrets versions access latest --secret="$sec_strava" \
        --impersonate-service-account="$sa_email_2" 2>&1)

    if [ $? -eq 0 ]; then
        echo "       ✅ Success. Secret accessed and captured."
    else
        # SECURITY ERROR: SA 2 failed to access its OWN secret.
        handle_failure "$sa_name_strava" "Required access to $sec_strava was DENIED." "$value_2B"
    fi

    # --- Final Conclusion ---
    if [ $overall_status -eq 0 ]; then
        echo "---------------------------------------------------------"
        echo "✅ SECURITY VERIFICATION PASSED: All 4 tests met expectations."
        return 0
    else
        echo "---------------------------------------------------------"
        echo "❌ SECURITY VERIFICATION FAILED: See errors above."
        return 1
    fi
}