import fitdecode
import csv
from datetime import datetime
from typing import List, Dict, Union
import io


def extract_track_points(fit_file_path: str) -> List[Dict[str, Union[float, str]]]:
    """
    Parses a FIT file and yields a list of dicts with lat, long, and time.
    Optimized for 'record' messages only.
    :param: fit_file_path: path to binary FIT file
    :return: list of dicts with lat, long, and time
    """

    points = []

    with fitdecode.FitReader(fit_file_path) as fit_file:
        for frame in fit_file:

            # We only care about data messages of type 'record'
            if frame.frame_type == fitdecode.FIT_FRAME_DATA and frame.name == 'record':

                # Check if this record actually has lat/long data
                if frame.has_field('position_lat') and frame.has_field('position_long'):
                    lat_raw = frame.get_value('position_lat')
                    lon_raw = frame.get_value('position_long')

                    if lat_raw is not None and lon_raw is not None:
                        # FIT stores coords in semicircles. Convert to degrees.
                        lat = lat_raw * (180 / 2 ** 31)
                        lon = lon_raw * (180 / 2 ** 31)
                        ts = frame.get_value('timestamp')

                        # Handle case where timestamp might be None or int
                        if isinstance(ts, datetime):
                            ts_iso = ts.isoformat()
                        else:
                            ts_iso = str(ts)

                        points.append({
                            'timestamp': ts_iso,
                            'latitude': lat,
                            'longitude': lon
                        })
    return points


def extract_points_from_csv_string(csv_data: str) -> List[Dict[str, Union[float, str]]]:
    """
    Parses a string containing CSV data and extracts track points.
    Assumes the CSV has 'latitude', 'longitude', and 'timestamp' columns.
    """
    points = []
    print("--- Starting CSV String Extraction ---")
    print(f"Received CSV data:\n---\n{csv_data}\n---")

    # Use io.StringIO to treat the string data as a file
    csv_file = io.StringIO(csv_data)
    
    # Use DictReader to easily access columns by name
    reader = csv.DictReader(csv_file)

    # --- DEBUG: Print detected field names ---
    print(f"CSV DictReader detected fieldnames: {reader.fieldnames}")
    
    for i, row in enumerate(reader):
        # --- DEBUG: Print each row as it's read ---
        print(f"Processing row {i}: {row}")
        try:
            # Extract and convert values, assuming they are already in degrees
            lat = float(row['latitude'])
            lon = float(row['longitude'])
            ts = row['timestamp']

            points.append({
                'timestamp': ts,
                'latitude': lat,
                'longitude': lon
            })
        except (KeyError, ValueError) as e:
            # Handle cases where columns are missing or values are not valid floats
            print(f"Skipping row due to error: {e}. Row: {row}")
            continue
            
    print(f"--- Finished CSV String Extraction, found {len(points)} points ---")
    return points


# Usage example for Data Engineering pipeline
def save_to_csv(points: List[Dict], output_file: str):
    if not points:
        return

    keys = points[0].keys()
    with open(output_file, 'w', newline='') as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(points)

if __name__ == "__main__":
    # --- Example for original FIT file usage ---
    ext = extract_track_points("1.fit")
    save_to_csv(ext, "1.csv")

    # --- Example for new in-memory CSV usage ---
#     # This is your CSV data, already decoded and stored in a string variable.
#     in_memory_csv = """timestamp,latitude,longitude
# 2023-10-27T10:00:00,40.7128,-74.0060
# 2023-10-27T10:00:05,40.7130,-74.0058
# 2023-10-27T10:00:10,40.7132,-74.0056
# """
#
#     # Extract points from the CSV string
#     extracted_points = extract_points_from_csv_string(in_memory_csv)
#
#     if not extracted_points:
#         print("Warning: No points were extracted from the in-memory CSV data. The output file will not be created.")
#     else:
#         # Save the extracted points to a new CSV file
#         save_to_csv(extracted_points, "from_memory.csv")
#         print(f"Extracted {len(extracted_points)} points from in-memory CSV and saved to from_memory.csv")
