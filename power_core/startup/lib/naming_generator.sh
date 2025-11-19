#!/bin/bash

#╔══════════════════════════════════════════╗
#║ Stage 1.1 Generate words                 ║
#╚══════════════════════════════════════════╝
get_validated_word() {

    local prompt_name="$1"
    local lenght="$2"
    local raw_input
    local input_length
    # Loop indefinitely until valid input is provided

    while true; do
        read -p "Enter ${prompt_name} (3-${lenght} lowercase letters a-z): " raw_input

        #convert uppercase to lowercase
        input_name=$(echo "$raw_input" | tr '[:upper:]' '[:lower:]')

        # Check the input length
        input_length=${#input_name}

        if [ "$input_length" -lt 3 ] || [ "$input_length" -gt ${lenght} ]; then

            echo "🯀 Invalid length. The ${prompt_name} must be between 3 and ${lenght} symbols." >&2

            continue # Restart the loop
        fi

        #  Check the content type using a regex pattern: ^[a-z]+$
        if [[ "$input_name" =~ ^[a-z]+$ ]]; then
            #  Success: Print the valid word to stdout and break the loop

            echo "$input_name"
            break
        else

            echo "🯀 Invalid characters. The ${prompt_name} must ONLY contain letters (a-z). Please remove any numbers or special symbols." >&2
            continue # Restart the loop
        fi
    done

}

#╔══════════════════════════════════════════╗
#║ Stage 1.2 Generate digits                ║
#╚══════════════════════════════════════════╝
generate_digits() {
    # 1. Generate the First Word: A 6-digit Number


    # Use /dev/urandom to generate random bytes,
    # convert to base-10 digits (0-9), and take the first 6 characters.
    # The 'tr -dc 0-9' part deletes all characters *not* in the 0-9 set.
    PREFIX_1=$(head /dev/urandom | tr -dc 0-9 | head -c 6)

    # Check if the generated number starts with '0'. While not strictly necessary
    # for a "symbol", it usually improves the look of a random 6-digit number.
    # A more complex loop could be used to guarantee no leading zero, but the
    # current method is simpler and fast enough.
    if [ ${#PREFIX_1} -lt 6 ]; then
        # Fallback/Retry if /dev/urandom didn't immediately yield 6 digits (rare)
        PREFIX_1=$(($RANDOM % 900000 + 100000))
    fi

    # 2. Generate the Second Word: One Letter (a-z) and One Digit (1-9)
    # --- Generate Random Letter (a-z) ---
    # Generate a random number between 0 and 25, then convert it to its
    # ASCII character equivalent, starting from 'a' (ASCII 97).
    RANDOM_CHAR_CODE=$(( ( RANDOM % 26 ) + 97 ))
    RANDOM_LETTER=$(printf \\$(printf '%o' $RANDOM_CHAR_CODE))

    # --- Generate Random Digit (1-9) ---
    # Generate a random number between 1 and 9 (inclusive)
    RANDOM_DIGIT=$(( ( RANDOM % 9 ) + 1 ))
    PREFIX_2="${RANDOM_LETTER}${RANDOM_DIGIT}"

    # ---- Create name for bucket
    RANDOM_DIGITS_B=$(($RANDOM % 900 + 100))
    # Generate 3 characters only from the set 'a-z'.
    RANDOM_LETTERS_B=$(head /dev/urandom | tr -dc 'a-z' | head -c 3)

    D1=${RANDOM_DIGITS_B:0:1}  # First digit
    D2=${RANDOM_DIGITS_B:1:1}  # Second digit
    D3=${RANDOM_DIGITS_B:2:1}  # Third digit
    L1=${RANDOM_LETTERS_B:0:1} # First letter
    L2=${RANDOM_LETTERS_B:1:1} # Second letter
    L3=${RANDOM_LETTERS_B:2:1} # Third letter

    # Combine them in the D-L-D-L-D-L sequence
    PREFIX_3="${D1}${L1}${D2}${L2}${D3}${L3}"

    # 3. Output and Store Results
    # Display the generated words
    echo "6-digit number): ${PREFIX_1}" &>/dev/null
    echo "Letter+Digit):  ${PREFIX_2}" &>/dev/null
    echo "Letter+Digit):  ${PREFIX_3}" &>/dev/null
    echo "------------------------------"
    export PREFIX_1
    export PREFIX_2
    export PREFIX_3
}

#╔══════════════════════════════════════════╗
#║ Stage 2.1 Build names                    ║
#╚══════════════════════════════════════════╝
build_resource_name() {
    local resource_type=$1
    local length_limit=$2
    local suffix_literal=$3
    shift 3 # Shifts $1, $2, $3 off, so "$@" now contains only the prompts

    local prompts=("$@")
    local name_parts=()
    local built_name=""

    echo "--- Starting Input Collection for ${resource_type} ---"

    # 1. Get all validated word parts
    for prompt in "${prompts[@]}"; do
        local part
        part=$(get_validated_word "${prompt}" "${length_limit}")
        name_parts+=("${part}") # Add part to our array
    done

    # 2. Run the generator
    # This (presumably) sets the $PREFIX_1, $PREFIX_2, $PREFIX_3 variables
    generate_digits

    # 3. Source the naming file
    # NOTE: Sourcing inside a loop is unusual. This re-loads the file every time.
    source ./lib/naming_generator.sh

    # 4. Evaluate the suffix
    # This safely evaluates the literal string (e.g., '${PREFIX_1}-${PREFIX_2}')
    # to get the actual values from the sourced file.
    local evaluated_suffix
    eval "evaluated_suffix=${suffix_literal}"

    # 5. Build the final name
    # Joins all name_parts with a hyphen
    built_name=$(IFS=-; echo "${name_parts[*]}")
    built_name="${built_name}-${evaluated_suffix}"

    # Set the global variable for the loop to use
    GENERATED_NAME="${built_name}"

    # Fixes the bug where both functions said "project name"
    echo "Your ${resource_type} name is: ${GENERATED_NAME}"
}

#╔══════════════════════════════════════════╗
#║ Stage 2.2 Show name to user for approve  ║
#╚══════════════════════════════════════════╝
user_input_check() {

    local CHOICE
    # Function prompts user for Y/N and sets exit status 0, 1, or 2

    read -r -p "Press Y to continue or N to repeat generate: " -n 1 CHOICE

    echo
    CHOICE=$(echo "$CHOICE" | tr '[:lower:]' '[:upper:]')
    if [ "$CHOICE" == "Y" ]; then

        return 0 # Y = Success/Break (Exit Code 0)
    elif [ "$CHOICE" == "N" ]; then

        return 1 # N = Failure/Repeat (Exit Code 1)
    else

        return 2 # Invalid Input (Exit Code 2)
    fi

}

run_generation_loop() {
    local generation_command=("$@") # Capture the command and all its args as an array

    # 1. Run the generation command *once* before the loop
    "${generation_command[@]}" || true

    # 2. Start the confirmation loop
    while true; do
        STATUS=0
        # Call the user_input_check function
        user_input_check || STATUS=$?

        if [[ $STATUS -eq 0 ]]; then
          echo "🮱 Continuing with the generated values."
          break # Exit the loop

        elif [[ $STATUS -eq 1 ]]; then
          echo "🔁 Repeating the generation process..."
          # Re-run the generation command passed to this function
          "${generation_command[@]}" || true

        elif [[ $STATUS -eq 2 ]]; then
          echo "🯀 Invalid input. Please enter Y or N."
          # Loop continues automatically

        else
          echo "🚨 An unexpected error occurred (Code $STATUS)."
          break
        fi
    done
}
