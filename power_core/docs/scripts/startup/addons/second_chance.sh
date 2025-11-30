#!/bin/bash
# Reusable


# Base code
# --- Configuration (Adjustable) ---
MAX_RETRIES=2 # Initial attempt + 1 retry = 2 total tries
RETRY_DELAY=20 # Wait 10 seconds between attempts

# --- The Retry Mechanism Function ---
# Arguments: Command_Name, Arg1, Arg2, ...
run_with_retry() {
    local command_to_run="$1"

    # Store all arguments *except* the command name (the first one)
    shift
    local command_args=("$@")

    local attempt=1
    local max_attempts=$MAX_RETRIES
    local last_exit_code=0

    # Loop for the maximum number of attempts (e.g., 1 and 2)
    while [ "$attempt" -le "$max_attempts" ]; do

        echo "      Attempt $attempt of $max_attempts: Running $command_to_run..."

        # Execute the command/function using its arguments
        # The '|| true' prevents set -e from killing the script if it fails
        "$command_to_run" "${command_args[@]}" || last_exit_code=$?

        # Check the exit status
        if [ "$last_exit_code" -eq 0 ]; then
            echo "🮱 $command_to_run succeeded on attempt $attempt."
            return 0 # Success! Exit the function with status 0
        fi

        # If it failed and this was the LAST attempt, exit with an error
        if [ "$attempt" -ge "$max_attempts" ]; then
            echo "🯀 $command_to_run failed after $max_attempts attempts." >&2
            echo "   Terminating script execution." >&2
            return 1 # Final failure! Exit the function with status 1
        fi

        # If it failed but has more retries, wait and continue
        echo "⚠ $command_to_run failed (Exit Code: $last_exit_code). Waiting $RETRY_DELAY seconds before retry."
        wait_and_counting_sheep "${RETRY_DELAY}"

        attempt=$(( attempt + 1 ))
    done
}

## Usage
#run_with_retry
#  function \
#  "first argument of function 1" \
#  "second argument of function 1"
#if [ $? -ne 0 ]; then exit 1; fi