import subprocess
import re
from pathlib import Path
import os
from typing import Iterable, Any, Generator
import tempfile

import logging
logger = logging.getLogger(__name__)

def is_safe_tmp_path(filepath: str) -> bool:
    """
    Validates that a filepath is:
    1. Absolute and located inside /tmp
    2. Has a safe filename (alphanumeric, dots, dashes, underscores, AND SPACES)
    3. Ends with .fit or .csv
    4. Does not begin with a dot; does not contain suspicious dot patterns
    5. Contains only printable ASCII characters
    """
    try:
        # Resolve handles symlinks and '..' relative segments
        path = Path(filepath).resolve()
        tmp_dir = Path("/tmp").resolve()

        # 1. Security: Ensure a path is strictly inside /tmp
        if not path.is_relative_to(tmp_dir):
            logger.warning(f"is_safe_tmp_path: Path {path} is not inside /tmp.")
            return False

        filename = path.name
        # 2. Validation: Check a filename pattern.
        # - Start with alphanumeric, not dot
        # - Only allowed characters, ends with .fit or .csv
        pattern = r"^(?!\.)([\w\-\. ]+)\.(fit|csv)$"
        # pattern = r"^[\w\-\. ]+\.(fit|csv)$" previous version

        if not re.fullmatch(pattern, filename, re.IGNORECASE):
            logger.warning(f"is_safe_tmp_path: Filename {filename} does not match required pattern.")
            return False
        # 3. No double dots, no dangerous dot patterns, only one extension
        if '..' in filename or filename.count('.') != 1:
            logger.warning(f"is_safe_tmp_path: Filename {filename} contains suspicious dot pattern.")
            return False

        # 4. Only printable ASCII
        if not all(32 <= ord(c) < 127 for c in filename):
            logger.warning(f"is_safe_tmp_path: Filename {filename} contains non-ASCII or non-printable characters.")
            return False

        logger.debug(f"is_safe_tmp_path: File {path} passed validation for command line use.")

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

    # --- FIT file format validation ---
    if flag == "-b":
        try:
            with open(input_path, 'rb') as f:
                header = f.read(14)
                if len(header) < 14 or header[8:12] != b'.FIT':
                    raise ValueError("Input file is not a valid .FIT file.")
        except FileNotFoundError:
            raise
        except ValueError as e:
            logger.error(f"FIT validation failed: {e}")
            raise
    elif flag == "-c":
        pass

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
    subprocess.run(command, check=True)
    #subprocess.run(command, check=True, shell=False)


def label_bike(data_stream: Iterable[str]) -> str:
    """
    Identifies the bike model (Strava gear_id) by searching the data stream
    for the first occurrence of a known sensor ANT device number. The search stops
    immediately upon finding the first matching code.
    :param data_stream: An iterable object yielding file lines (the file object itself).
    :return: The corresponding gear_id b1234567 or a stopgap ID b0000000 if no match is found.
    """
    # 1. Define the sensor codes and their associated gear_ids
    GEAR_MAPPING = {
        'ant_device_number,"4315"': 'b7647614',  # MTB Code 1
        'ant_device_number,"33509"': 'b7647614',  # MTB Code 2
        'ant_device_number,"2230"': 'b8850168',  # Gravel Code 1
        'ant_device_number,"9560"': 'b8850168',  # Gravel Code 2
    }
    # 2. Iterate through the entire stream until a match is found
    # This automatically handles the "read in chunks" requirement.
    for line in data_stream:
        # Check for any of the sensor codes in the current line
        for code, gear_id in GEAR_MAPPING.items():
            if code in line:
                # 3. Stop search and return immediately upon the first match
                logger.debug(f"Bike labeled with gear_id: {gear_id} (Code: {code})")
                return gear_id
    logger.info("No matching ANT device number found. Using stopgap ID.")
    return 'b0000000'


def clean_data_stream(data_stream: Iterable[str]) -> Generator[tuple[str, bool, int], Any, None]:
    """
    Processes a stream of text lines, applying cleaning and yielding results.
    :param data_stream: An iterable object yielding file lines (e.g., the file object itself).
    Yields:
        A tuple containing the cleaned line (str) and the count of changes made (int).
    """
    # Pre-compile regex patterns for efficiency
    LAT_PATTERN = re.compile(r'position_lat,"(-?\d+)",semicircles,position_long,"-?\d+",semicircles,')
    SERIAL_NUMBER_PATTERN = re.compile(r'serial_number,"SN\.(\d+)"')
    changes_count = 0
    validation_failed = False

    # 1. Get bike model (needs to be done before the main loop starts consuming the stream)
    # Note: If label_bike consumes the stream, you must find another way
    # to label the bike, perhaps by reading a small header section separately.

    for line in data_stream:
        original_line = line

        if line.startswith("Data"):
            # 2. Lat value check (negative lat deletion)
            match_lat = LAT_PATTERN.search(line)
            if match_lat:
                try:
                    lat_value = int(match_lat.group(1))
                    if lat_value < 0:
                        validation_failed = True
                        # Delete the fragment if lat is negative
                        line = line.replace(match_lat.group(0), "")
                        changes_count += 1
                except ValueError:
                    # Handle cases where match_lat.group(1) is not an integer
                    pass

            # 3. Serial number fix
            line = SERIAL_NUMBER_PATTERN.sub(r'serial_number,"\1"', line)

        yield line, validation_failed, changes_count


def cleaner_run(input_path: str, output_path: str, pipeline: str):
    """
    Run analyze the .csv file in stream mode, without loading it in memory
    :param input_path:
    :param output_path:
    :param pipeline: 'public' or 'private'
    :return:
    """
    temp_file_name = None
    validation_failed = False
    logger.debug(f"Starting GPS cleaning for '{input_path}'.")

    if not is_safe_tmp_path(input_path):
        raise ValueError(f"Unsafe input_path for GPS cleaning: {repr(input_path)}")
    if not is_safe_tmp_path(output_path):
        raise ValueError(f"Unsafe output_path for GPS cleaning: {repr(output_path)}")

    try:
        with open(input_path, 'r', encoding='utf-8') as infile_label:
            bike_model_id = label_bike(infile_label)
            print(f"Identified Bike Model ID: {bike_model_id}")
        with open(input_path, 'r', encoding='utf-8') as infile_clean:
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as temp_outfile:
                temp_file_name = temp_outfile.name
                logger.debug(f"Writing to temporary file: {temp_file_name}")
                for cleaned_line, current_validation_status, changes_count in clean_data_stream(infile_clean):
                    temp_outfile.write(cleaned_line)
                    validation_failed |= current_validation_status
                print("Delete issues: ", changes_count)
        if not validation_failed and pipeline == "public":
            logger.warning("File passed all integrity checks. Output file is NOT written/needed.")
            os.remove(temp_file_name)
        elif validation_failed and pipeline == "public":
            logger.warning("Integrity check FAILED. File needed cleaning and is being saved.")
            os.rename(temp_file_name, output_path)
        elif pipeline == "private":
            os.rename(temp_file_name, output_path)
    except FileNotFoundError:
        logger.error(f"Error: Input file not found at {input_path}")
        if temp_file_name and os.path.exists(temp_file_name):
            os.remove(temp_file_name)
    except Exception as e:
        logger.critical(f"A fatal error occurred: {e}")
        if temp_file_name and os.path.exists(temp_file_name):
            os.remove(temp_file_name)
    return bike_model_id, changes_count


def load_email_template(locale: str, result : str) -> tuple[str, str]:
    """
    Loads email subject and body from template files based on locale.
    :param locale: The desired language ('en', 'uk', etc.).
    :param result: 'find' or 'not_found'

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

if __name__ == '__main__':
 # Test locally running. Path's is a system temp folder in the root
    import time
    test_input_path = "/tmp/problem_fit1.csv"
    test_output_path = "/tmp/resolved_fit3.csv"
    test_run = time.perf_counter()
    cleaner_run(test_input_path, test_output_path, pipeline="public")
    test_end = time.perf_counter()
    runtime_core = test_end - test_run
    print(f"Core execute speed: {runtime_core:.9f} seconds")
