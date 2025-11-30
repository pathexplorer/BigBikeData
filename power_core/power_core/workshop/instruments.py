import subprocess
import re
from pathlib import Path
import os
import time

import logging
logger = logging.getLogger(__name__)

def is_safe_tmp_path(filepath: str) -> bool:
    """
    Validates that a filepath is:
    1. Absolute and located inside /tmp
    2. Has a safe filename (alphanumeric, dots, dashes, underscores, AND SPACES)
    3. Ends with .fit or .csv
    """
    try:
        # Resolve handles symlinks and '..' relative segments
        path = Path(filepath).resolve()
        tmp_dir = Path("/tmp").resolve()

        # 1. Security: Ensure a path is strictly inside /tmp
        if not path.is_relative_to(tmp_dir):
            return False

        # 2. Validation: Check filename pattern
        # Added space '' to the character class: [\w\-\. ]
        filename = path.name
        pattern = r"^[\w\-\. ]+\.(fit|csv)$"

        if not re.fullmatch(pattern, filename, re.IGNORECASE):
            return False

        return True

    except (TypeError, ValueError):
        # Returns False for None or malformed paths
        return False

def convert_fit_to_csv(input_path, output_path, mode):
    """
    Converts a .fit file to .csv or vice versa using the FitCSVTool.jar.
    It uses an absolute path to the .jar file to ensure it runs correctly
    in any environment (local or container).
    """
    # Security check of the file paths
    if not is_safe_tmp_path(input_path):
        raise ValueError(f"Unsafe input_path for FIT decode: {repr(input_path)}")
    if not is_safe_tmp_path(output_path):
        raise ValueError(f"Unsafe output_path for FIT decode: {repr(output_path)}")

    flag = "-b" if mode == "decode" else "-c"

    # --- Path Correction ---
    # Get the directory where this Python script is located.
    # In the container, this will be /app/power_core/workshop
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Construct the absolute path to the .jar file.
    # It is located in the parent directory of 'workshop' (i.e., 'power_core').
    # The path will resolve to /app/power_core/FitCSVTool.jar in the container.
    jar_path = os.path.join(script_dir, '..', 'FitCSVTool.jar')
    
    # Normalize the path to resolve the '..' component.
    jar_path = os.path.normpath(jar_path)

    logger.debug(f"Attempting to use FitCSVTool.jar at: {jar_path}")

    # --- Execute the Command ---

    command = ["java", "-jar", jar_path, flag, input_path, output_path]



    # Check if the JAR file actually exists before running the command
    if not os.path.exists(jar_path):
        raise FileNotFoundError(f"FATAL: The JAR file could not be found at the expected path: {jar_path}")
    start = time.perf_counter()
    subprocess.run(command, check=True)
    #subprocess.run(command, check=True, shell=False)
    end = time.perf_counter()
    runtime_core = end - start
    logger.info(f"Core execute speed: {runtime_core:.3f} seconds")

def label_bike(lines):
    """
    Getting bike model
    :param lines:
    :return: in Strava gear_id is the registered name of the bike
    """
    mtb = ['ant_device_number,"4315"', 'ant_device_number,"33509"']
    gravel = ['ant_device_number,"2230"', 'ant_device_number,"9560"']
    for line in lines:
        if any(code in line for code in mtb):
            return 'b7647614'
        if any(code in line for code in gravel):
            return 'b8850168'
    return 'b0000000' # stopgap if sensors are discharge

def clean_gps(input_path: str, output_path: str, pipeline: str) -> tuple[str, int]:
    """
    Processes a CSV file to clean GPS errors and fix sensor serial numbers.

    Args:
        input_path: The absolute path to the source CSV file.
        output_path: The absolute path where the cleaned CSV will be saved.
        pipeline: 'public' or 'private', to determine file-saving behavior.

    Returns:
        A tuple containing (detected_bike_model_id, number_of_changes).

    Raises:
        ValueError: If input or output paths are invalid or unsafe.
        FileNotFoundError: If the input file does not exist.
        IOError: If there is an error reading or writing files.
    """
    logger.debug(f"Starting GPS cleaning for '{input_path}'.")

    if not is_safe_tmp_path(input_path):
        raise ValueError(f"Unsafe input_path for GPS cleaning: {repr(input_path)}")
    if not is_safe_tmp_path(output_path):
        raise ValueError(f"Unsafe output_path for GPS cleaning: {repr(output_path)}")

    try:
        with open(input_path, 'r', encoding='utf-8') as infile:
            lines = infile.readlines()

        bike_model = label_bike(lines)
        cleaned_lines = []
        changes_count = 0
        
        lat_pattern = re.compile(r'position_lat,"(-?\d+)",semicircles,position_long,"-?\d+",semicircles,')

        for line in lines:
            if line.startswith("Data"):
                match = lat_pattern.search(line)
                if match:
                    lat_value = int(match.group(1))
                    if lat_value < 0:
                        line = line.replace(match.group(0), "")  # Delete fragment
                        changes_count += 1

                # There resolving exceptions, which can terminate a convert process
                # Actual for records before 01/10/2025, but a problem can reopen with users' files
                line = re.sub(r'serial_number,"SN\.(\d+)"', r'serial_number,"\1"', line)
            
            cleaned_lines.append(line)

        if changes_count > 0:
            logger.info(f"Detected and fixed {changes_count} issues in the data.")
        else:
            logger.info("No data issues found that required cleaning.")

        # For the public 'repair' flow, if no changes were made, we can skip writing the file.
        # For the private pipeline, we must write the file for the next stage.
        if pipeline == "public" and changes_count == 0:
            logger.warning("Public pipeline: No changes made, so not writing a new CSV.")
            return bike_model, 0

        with open(output_path, 'w', encoding='utf-8') as outfile:
            outfile.writelines(cleaned_lines)
        
        logger.info(f"Successfully cleaned GPS data and saved to '{output_path}'. Detected bike: {bike_model}.")
        return bike_model, changes_count

    except FileNotFoundError:
        logger.error(f"Input file not found during GPS cleaning: {input_path}")
        raise
    except IOError as e:
        logger.error(f"IOError during GPS cleaning from '{input_path}' to '{output_path}': {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during clean_gps: {e}")
        raise


def load_email_template(locale: str, result : str) -> tuple[str, str]:
    """
    Loads email subject and body from template files based on locale.

    Args:
        locale: The desired language ('en', 'uk', etc.).
        result: 'find' or 'not_found'

    Returns:
        A tuple containing the (subject_template, body_template).
        Defaults to English if the specified locale is not found.

    """
    # Determine the base path of the templates directory
    type_of_email = None
    if result == "find":
        type_of_email = 'email'
    elif result == "not_found":
        type_of_email = 'warning_email'

    base_path = os.path.join(os.path.dirname(__file__), '..', 'templates', type_of_email)
    # Default to 'en' if the locale is not supported
    if locale not in ['en', 'uk']:
        locale = 'en'

    subject_path = os.path.join(base_path, f'{locale}_subject.txt')
    body_path = os.path.join(base_path, f'{locale}_body.html')

    try:
        with open(subject_path, 'r', encoding='utf-8') as f:
            subject_template = f.read()
        with open(body_path, 'r', encoding='utf-8') as f:
            body_template = f.read()
        return subject_template, body_template
    except FileNotFoundError as e:
        logger.error(f"Could not find email template for locale '{locale}': {e}. Defaulting to 'en'.")
        # Explicitly load English templates as a fallback
        subject_path = os.path.join(base_path, 'en_subject.txt')
        body_path = os.path.join(base_path, 'en_body.html')
        with open(subject_path, 'r', encoding='utf-8') as f:
            subject_template = f.read()
        with open(body_path, 'r', encoding='utf-8') as f:
            body_template = f.read()
        return subject_template, body_template