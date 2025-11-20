import subprocess
import re
import os

def convert_fit_to_csv(input_path, output_path, mode):
    """
    Converts a .fit file to .csv or vice-versa using the FitCSVTool.jar.
    It uses an absolute path to the .jar file to ensure it runs correctly
    in any environment (local or container).
    """
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

    print(f"DEBUG: Attempting to use FitCSVTool.jar at: {jar_path}")

    # --- Execute the Command ---
    command = ["java", "-jar", jar_path, flag, input_path, output_path]
    
    # Check if the JAR file actually exists before running the command
    if not os.path.exists(jar_path):
        raise FileNotFoundError(f"FATAL: The JAR file could not be found at the expected path: {jar_path}")
        
    subprocess.run(command, check=True)


def label_bike(lines):
    """
    Getting bike model
    :param lines:
    :return: in Strava gear_id is registered name of bike
    """
    mtb = ['ant_device_number,"4315"', 'ant_device_number,"33509"']
    gravel = ['ant_device_number,"2230"', 'ant_device_number,"9560"']
    for line in lines:
        if any(code in line for code in mtb):
            return 'b7647614'
        if any(code in line for code in gravel):
            return 'b8850168'
    return 'b0000000' # stopgap if sensors are discharge

def clean_gps(input_path, output_path):
    """
    Processing CSV for clean from GPS problems, fix incorrect sensor serial number
    """
    # Finding lat, long and gps_accuracy
    pattern = re.compile(
       r'position_lat,"(-?\d+)",semicircles,position_long,"-?\d+",semicircles,'
    )
    with open(input_path, 'r', encoding='utf-8') as infile:
        lines = infile.readlines()
    bike_model = label_bike(lines)
    cleaned_lines = []
    for line in lines:
        if line.startswith("Data"):
            match = pattern.search(line)
            if match:
                lat_value = int(match.group(1))
                if lat_value < 0:
                    line = line.replace(match.group(0), "")  # Видаляємо фрагмент
            #for records before 01/10/2025
            line = re.sub(r'serial_number,"SN\.(\d+)"', r'serial_number,"\1"', line)
        cleaned_lines.append(line)
    with open(output_path, 'w', encoding='utf-8') as outfile:
        outfile.writelines(cleaned_lines)
    return bike_model
