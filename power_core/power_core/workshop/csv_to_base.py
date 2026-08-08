"""
GPS Data Processor (Memory Stream to PostgreSQL)
Target: Psycopg 3 (Modern Python)
"""
import csv
import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Iterator, Optional
from power_core.database.db_conect import load_stream_to_postgres

logger = logging.getLogger(__name__)

# --- Configuration & Constants ---
GARMIN_EPOCH = datetime(1989, 12, 31, 0, 0, 0, tzinfo=timezone.utc)
SEMICIRCLE_CONVERSION_FACTOR = 180.0 / (2**31)

# --- Domain Exceptions ---
class DataProcessingError(Exception):
    """Raised when raw CSV values cannot be parsed into a valid GPS record."""

# --- Transformation Logic ---
def convert_semicircles_to_degrees(semicircles: str | int) -> float:
    """Convert a FIT semicircle coordinate value into decimal degrees."""
    try:
        val = int(semicircles)
        return val * SEMICIRCLE_CONVERSION_FACTOR
    except (ValueError, TypeError) as e:
        raise DataProcessingError(f"Invalid semicircle value: {semicircles}") from e


def convert_garmin_timestamp(timestamp_val: str | int) -> str:
    """Convert a Garmin epoch (1989-12-31) seconds value into an ISO-8601 timestamp string."""
    try:
        seconds = int(timestamp_val)
        return (GARMIN_EPOCH + timedelta(seconds=seconds)).isoformat()
    except (ValueError, TypeError) as e:
        raise DataProcessingError(f"Invalid timestamp value: {timestamp_val}") from e


# --- Parser Logic (Generator) ---
def parse_memory_csv_stream(input_data: str) -> Iterator[tuple[str, float, float]]:
    """
    Yields parsed rows one by one. No large lists created in memory.
    """
    f = io.StringIO(input_data)
    reader = csv.reader(f)

    for row_idx, row in enumerate(reader):
        if not row:
            continue

        # Basic structure check: Data, 0, record...
        # FIX: Strip leading whitespace from the first field to match correctly.
        if len(row) < 3 or row[0].strip() != "Data" or row[2] != "record":
            continue

        ts_val: Optional[str] = None
        lat_val: Optional[str] = None
        lon_val: Optional[str] = None

        # Extract fields dynamically
        try:
            for i in range(3, len(row) - 1, 3):
                field_name = row[i]
                field_val = row[i + 1]

                if field_name == "timestamp":
                    ts_val = field_val
                elif field_name == "position_lat":
                    lat_val = field_val
                elif field_name == "position_long":
                    lon_val = field_val

                if ts_val and lat_val and lon_val:
                    break

            if ts_val and lat_val and lon_val:
                yield (
                    convert_garmin_timestamp(ts_val),
                    convert_semicircles_to_degrees(lat_val),
                    convert_semicircles_to_degrees(lon_val)
                )
        except Exception as e:
            logger.warning(f"Skipping malformed row {row_idx}: {e}")
            continue

# --- Main Execution ---
def process_data(raw_java_csv_string: str):
    """Stream parsed GPS rows from the raw CSV string into PostgreSQL."""
    logger.info("Starting Psycopg 3 Pipeline...")

    # Create the generator
    data_stream = parse_memory_csv_stream(raw_java_csv_string)

    # Pipe generator directly to DB loader
    load_stream_to_postgres(data_stream)


if __name__ == "__main__":
    from gcp_actions.common_utils.handle_logs import run_handle_logs
    from gcp_actions.common_utils.local_runner import check_cloud_or_local_run
    run_handle_logs()
    check_cloud_or_local_run()
    # Test Data
    MOCK_INPUT = """
    Data,0,file_id,serial_number,"12345",,,,,
    Data,0,record,timestamp,"1123857194",s,position_lat,"590331176",semicircles,position_long,"381401975",semicircles,gps_accuracy,"2",m,distance,"0.0",m
    Data,0,record,timestamp,"1123857195",s,position_lat,"590331000",semicircles,position_long,"381401900",semicircles,gps_accuracy,"2",m,distance,"1.0",m
        """
    process_data(MOCK_INPUT)