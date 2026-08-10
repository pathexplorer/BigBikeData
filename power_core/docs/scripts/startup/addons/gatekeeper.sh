#!/bin/bash
# REUSABLE: base code and injection part
# -- The "Switcher" / Gatekeeper Function ---

# Base code. Locate in own catalog
run_stage() {
    local stage_name=$1
    # Check if the stage name is in the state file
    if grep -q "^${stage_name}$" "$STATE_FILE"; then
        # If found, skip this stage
        echo "🮱 Stage '$stage_name' already completed. Skipping."
    else
        # If not found, run the stage
        echo " ▷ Running stage: $stage_name..."
        local exit_code=0
        # This calls the function whose name matches the $stage_name variable
        # We add '|| true' to prevent 'set -e' (when it used) from stopping the script
        # before we can check the exit code.
        "$stage_name" || exit_code=$?

        # Capture the exit code of the function
        #local exit_code=$?

        if [ $exit_code -eq 0 ]; then
            # If success (code 0), log it and continue
            echo "🮱 Stage '$stage_name' finished successfully. Logging."
            echo "$stage_name" >> "$STATE_FILE"
        else
            # If failure (any non-zero code), stop the script
            echo "🯀 ERROR: Stage '$stage_name' failed with exit code $exit_code. Stopping."
            exit 1
        fi
    fi
}

# Injection part
# 1\2 Insert in main.sh in header (after loading source)

#STATE_FILE="script_progress.log"
#export STATE_FILE
#touch "$STATE_FILE"
#
## Handle a "reset" argument to clear the log
## Run: ./start.sh reset
#if [ "$1" == "reset" ]; then
#    echo "Resetting state file..."
#    > "$STATE_FILE" # This clears the file
#fi

# 2/2 Insert in main.sh in body

#stage_1() {
#    echo
#    return 0 # Success
#}

#stage_2() {
#    echo
#    return 0 # Success
#}

## Run each stage through the "switcher"
#run_stage "stage_1"
#run_stage "stage_2"

#echo "🮱 All stages completed successfully."
