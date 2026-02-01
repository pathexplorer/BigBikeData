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





# Usage example for Data Engineering pipeline
def save_to_csv(points: List[Dict], output_file: str):
    if not points:
        return

    keys = points[0].keys()
    with open(output_file, 'w', newline='') as f:
        dict_writer = csv.DictWriter(f, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(points)

# if __name__ == "__main__":
#     # --- Example for original FIT file usage ---
#     # ext = extract_track_points("1.fit")
#     # save_to_csv(ext, "1.csv")


