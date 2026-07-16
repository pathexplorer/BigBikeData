#!/bin/bash
# REUSABLE: base code, injection only functions and echo statement

# Base code
# --- GLOBAL TIMER VARIABLES ---
# Exporting these variables ensures they are shared across all sourced scripts
# and all functions called within the same shell process.
export TIMER_START_EPOCH=0
export TIMER_TOTAL_SECONDS=0

# Function to start (or resume) the timer
timer_start() {
    # Check if the timer is already running (START_EPOCH != 0)
    if [ "$TIMER_START_EPOCH" -eq 0 ]; then
        # Record the current time in seconds since epoch
        # The 'export' is a good practice but is not strictly necessary here
        # since it's already a global, non-local variable.
        TIMER_START_EPOCH=$(date +%s)
        echo "DEBUG: Timer Started at UTC $TIMER_START_EPOCH" &>/dev/null
    else
        # This handles cases where timer_start might be accidentally called twice
        echo "DEBUG: Timer already running. Start UTC time: $TIMER_START_EPOCH. New Total: $TIMER_TOTAL_SECONDS"
    fi
}

# Function to stop (pause) the timer and add the elapsed time to the total
timer_pause() {
    # Check if the timer is actually running (START_EPOCH != 0)
    if [ "$TIMER_START_EPOCH" -ne 0 ]; then
        # 1. Calculate current time
        local current_epoch=$(date +%s)
        # 2. Calculate the elapsed time in seconds
        local elapsed_seconds=$((current_epoch - TIMER_START_EPOCH))
        # 3. Add elapsed time to the total (updates the global variable)
        TIMER_TOTAL_SECONDS=$((TIMER_TOTAL_SECONDS + elapsed_seconds))
        # 4. Reset the start time to 0 to signal the timer is paused/stopped
        TIMER_START_EPOCH=0
        echo "DEBUG: Timer Paused. Added $elapsed_seconds seconds. New Total: $TIMER_TOTAL_SECONDS"
    else
        # If START_EPOCH is 0, it means the timer is already paused or was never started.
        echo "DEBUG: Timer already Paused. Added 0 seconds. New Total: $TIMER_TOTAL_SECONDS"
    fi
}

# Injection part
#Insert at the end of the script
#timer_pause
#echo "Total Execution Time (excluding user pauses): ${TIMER_TOTAL_SECONDS} seconds"