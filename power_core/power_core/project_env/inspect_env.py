"""
Script runs after open the project and shows current variables
"""
import os
import re
from dotenv import load_dotenv
from typing import Set
from datetime import datetime

dotenv_path = os.path.join(os.path.dirname(__file__), "/home/stas/mega/projects/BigBikeData/keys.env")
load_dotenv(dotenv_path=dotenv_path, override=False)



def get_env_vars_from_file(file_path: str) -> Set[str]:
    """Reads a .env file and returns a set of variable names defined within it."""
    var_names = set()
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                match = re.match(r'([A-Z0-9_]+)=', line)
                if match:
                    var_names.add(match.group(1))
    except FileNotFoundError:
        # In a real application, you might raise an exception here
        pass
    return var_names


def inspect_loaded_vars_table(env_file_path: str):
    """
    Compares file variables to the active Python environment and prints them
    in a two-column table format.
    """

    # 1. Get names from the .env file
    target_vars = get_env_vars_from_file(env_file_path)

    if not target_vars:
        print("--- DEBUG: No variable names found in the specified .env file. ---")
        return

    # --- Table Setup ---
    # Define widths for columns
    KEY_WIDTH = 30
    VALUE_WIDTH = 85
    SEPARATOR = "-" * (KEY_WIDTH + VALUE_WIDTH + 7)  # Total width of the table

    print(SEPARATOR)
    print(f"| {'VARIABLE NAME':<{KEY_WIDTH}} | {'VALUE':<{VALUE_WIDTH}} |")
    print(SEPARATOR)

    # 2. Iterate through os.environ and print matching variables
    found_count = 0
    for key in os.environ.keys():
        if key in target_vars:
            value = os.environ[key]

            # Truncate long values for clean table output
            if len(value) > VALUE_WIDTH:
                value = value[:VALUE_WIDTH - 4] + "..."  # Truncate and add ellipsis

            # Use f-string formatting with < for left-alignment
            print(f"| {key:<{KEY_WIDTH}} | {value:<{VALUE_WIDTH}} |")
            found_count += 1

    print(SEPARATOR)

    if found_count == 0:
        print("🯀 No matching variables found in the current environment (os.environ).")
    else:
        current_datetime = datetime.now()
        formatted_time_24hr = current_datetime.strftime("%H:%M:%S")
        print(f"🮱 {formatted_time_24hr} Successfully found {found_count} of {len(target_vars)} expected variables.")


if __name__ == "__main__":
     # absolute path to .env file
    ENV_FILE = os.path.expanduser('/home/stas/mega/projects/BigBikeData/keys.env')

    inspect_loaded_vars_table(ENV_FILE)