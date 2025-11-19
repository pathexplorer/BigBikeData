#!/bin/bash

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
