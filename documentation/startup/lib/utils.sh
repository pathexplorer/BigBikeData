#!/bin/bash

# Dry-run wrapper: prints command instead of executing if DRY_RUN=true.
# Executes via "$@" (NOT eval) so arguments with spaces, e.g.
# --display-name="Dropbox Service Account", are preserved verbatim.
run_cmd() {
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "🔍 [DRY-RUN] Would execute: $*"
        return 0
    else
        "$@"
    fi
}

check_required_variables() {
  local var_list=("$@") # Takes all arguments as an array of variable names to check
  local all_good=true
  echo "-----------------------------------------------------------------------"
  echo "- 1. Running Pre-flight Variable Check..."
  echo "-----------------------------------------------------------------------"
  # Print the table header
  printf "%-35s %s\n" "VARIABLE" "VALUE"
  printf "%-35s %s\n" "-------------------------" "-----------------------------------"
  # Iterate over each variable name passed to the function
  for var_name in "${var_list[@]}"; do
    # Use indirect expansion to get the variable's value
    local var_value="${!var_name}"

    # Check if the value is zero-length (empty)
    if [[ -z "$var_value" ]]; then
      echo "🯀 ERROR: Required variable '$var_name' is not set or is empty."
      all_good=false
    else
      printf "🮱 %-35s %s\n" "$var_name" "$var_value"
    fi
  done

  if ! $all_good ; then
    echo "------------------------------------------------"
    echo "SCRIPT ABORTED: Please set all missing variables and try again."
    exit 1
  fi
echo "🮱 All required variables are set."
echo "------------------------------------------------"
}

# Append "KEY=VALUE" to names.env only if the KEY is not already present,
# preventing duplicate entries when the script is re-run.
append_env_value() {
  local key_value="$1"
  local env_file="${2:-names.env}"
  local key="${key_value%%=*}"
  local value="${key_value#*=}"
  if [[ -z "$value" ]]; then
    echo "⚠️  $key is empty; will record it when a value is available."
    return 0
  fi
  if grep -q "^${key}=" "$env_file" 2>/dev/null; then
    echo "🮱 $key already recorded in $env_file. Skipping."
  else
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        echo "🔍 [DRY-RUN] Would record $key_value in $env_file"
    else
        echo "$key_value" >> "$env_file"
        echo "🮱 Recorded $key_value in $env_file."
    fi
  fi
}
