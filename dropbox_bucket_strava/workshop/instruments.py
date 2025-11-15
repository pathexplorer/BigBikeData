import subprocess
import re

def convert_fit_to_csv(input_path, output_path, mode):
    flag = "-b" if mode == "decode" else "-c"
    subprocess.run(["java", "-jar", "FitCSVTool.jar", flag, input_path, output_path], check=True)

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

