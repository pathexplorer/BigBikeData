#!/bin/bash

# Function to verify both service accounts have access to the combined
# Dropbox+Strava secret and are denied access to the fullstack JSON keys secret.
# Arguments: sa_name_dropbox, sa_name_strava, sec_dropbox, sec_fullstack_json_keys, sa_email_1, sa_email_2
sa_binding_verif() {
    local sa_name_dropbox="$1"
    local sa_name_strava="$2"
    local sec_dropbox="$3"
    local sec_fullstack_json_keys="$4"
    local sa_email_1="$5"
    local sa_email_2="$6"
    local overall_status=0 # 0 means all tests passed

    echo "4. Verifying security access bindings..."

    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "🔍 [DRY-RUN] Would verify security bindings for:"
        echo "🔍 [DRY-RUN]   - $sa_name_dropbox ($sa_email_1) -> $sec_dropbox (allowed), $sec_fullstack_json_keys (denied)"
        echo "🔍 [DRY-RUN]   - $sa_name_strava ($sa_email_2) -> $sec_dropbox (allowed), $sec_fullstack_json_keys (denied)"
        return 0
    fi

    # --- Helper function to display detailed failure message ---
    # $1: SA Name, $2: Secret Name, $3: Error Message
    handle_failure() {
        echo "       [❌ FAIL] $1 TEST FAILED: $2" >&2
        echo "       Reason: $3" >&2
        overall_status=1 # Set failure flag
    }

    # --- Helper to run a single access test ---
    # $1: SA Name, $2: Secret Name, $3: SA Email
    # 0 = access expected to succeed, 1 = access expected to be denied
    access_test() {
        local sa_name="$1"
        local secret="$2"
        local sa_email="$3"
        local expected=$4

        echo "     - Accessing $secret (REQUIRED if expected=0, FORBIDDEN if expected=1):"

        local output
        output=$(gcloud secrets versions access latest --secret="$secret" \
            --impersonate-service-account="$sa_email" 2>&1)

        if [ $? -eq 0 ]; then
            if [ "$expected" -eq 0 ]; then
                echo "       ✅ Success. Secret accessed."
            else
                handle_failure "$sa_name" "Forbidden access to $secret was GRANTED." "Value: $output"
            fi
        else
            if [ "$expected" -eq 1 ]; then
                echo "       ✅ Success. Access was correctly denied."
            else
                handle_failure "$sa_name" "Required access to $secret was DENIED." "$output"
            fi
        fi
    }

    # --- Test Group 1: SA 1 (dropbox-manager) ---
    echo "   Testing permissions for $sa_name_dropbox ($sa_email_1)..."
    access_test "$sa_name_dropbox" "$sec_dropbox" "$sa_email_1" 0
    access_test "$sa_name_dropbox" "$sec_fullstack_json_keys" "$sa_email_1" 1

    # --- Test Group 2: SA 2 (strava-manager) ---
    echo "   Testing permissions for $sa_name_strava ($sa_email_2)..."
    access_test "$sa_name_strava" "$sec_dropbox" "$sa_email_2" 0
    access_test "$sa_name_strava" "$sec_fullstack_json_keys" "$sa_email_2" 1

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
