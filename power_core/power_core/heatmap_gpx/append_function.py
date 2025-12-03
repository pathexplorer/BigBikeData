"""
Append one file to one in binary mode for economy
After all, delete an original GPX file of activity
"""
import os
import re
from power_core.project_env.config import LOCAL_TMP
from gcp_actions.client import get_bucket, get_any_client
from gcp_actions.blob_manipulation import upload_to_gcp_bucket, delete_blob
from google.cloud import firestore

import logging

logger = logging.getLogger(__name__)

bucket_name = "GCS_BUCKET_NAME"


def extract_first_time_tag(file_path: str) -> str | None:
    """
    :param file_path:
    :return:
    """
    try:
        time_pattern = re.compile(r"<time>(.*?)</time>")
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                match = time_pattern.search(line)
                if match:
                    return match.group(1)
        return None
    except FileNotFoundError:
        logger.error(f"File not found at path: {file_path}")
        raise
    except IOError as e:
        logger.error(f"IOError processing file '{file_path}': {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred in extract_first_time_tag for '{file_path}': {e}")
        raise

def strip_source_content(file_path: str) -> None:
    """
    Strips the GPX file header and footer in-place to prepare it for concatenation.
    This function reads a GPX file, removes the first two lines (XML declaration
    and <gpx> tag) and the last line (</gpx> tag), and overwrites the file
    with the stripped content.
    Args:
        file_path: The absolute path to the GPX file to be modified.
    Raises:
        FileNotFoundError: If the specified file_path does not exist.
        IOError: If there is an error reading from or writing to the file.
        Exception: For any other unexpected errors.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= 2:
            logger.warning(f"File '{file_path}' has too few lines to be stripped. Skipping.")
            return
        # Remove the first two lines and the last line
        stripped_lines = lines[2:-1]
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(stripped_lines)
        logger.debug(f"Successfully stripped header/footer from '{file_path}'.")

    except FileNotFoundError:
        logger.error(f"File not found at path: {file_path}")
        raise
    except IOError as e:
        logger.error(f"IOError processing file '{file_path}': {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred in strip_source_content for '{file_path}': {e}")
        raise


def append_gpx_via_compose(local_gpx: str, bike_model: str, gpx_gcs_path: str = None) -> None:
    """
    gpx_gcs_path: if enable functional for delete a GPX file after appending to heatmap and GIS analyze (coming soon)
    """
    bucket = get_bucket(bucket_name)
    db = get_any_client("firestore")
    max_compose = 32

    # Forming name list for branch
    branch = {
            'b7647614': ['mtb', 'mtb_index.txt', 'mtb_compose_state.json'],
            'b8850168': ['gravel', 'gravel_index.txt', 'gravel_compose_state.json'],
            'b0000000': ['unknown', 'unknown_index.txt', 'unknown_compose_state.json'],
    }.get(bike_model)
    if branch is None:
        logger.warning(f"Unknown bike_model: {bike_model}")
        return

    gpx_name, index_name, compose_name = branch
    index_doc_name = index_name.replace('.txt', '')


    # Load state from the Firestore
    specs_ref = db.collection('heatmap').document('specs')
    specs_doc = specs_ref.get()
    if specs_doc.exists:
        specs_data = specs_doc.to_dict()
        state = specs_data.get(gpx_name)
        if not state:
            # This case can happen if a new bike type is added but not yet in Firestore
            ver = '00'
            state = {
                "main_blob_name": f"heatmap/{gpx_name}_v{ver}.gpx",
                "compose_count": 0,
                "version": 0,
            }
    else:
        # Create an initial spec doc if it doesn't exist
        logger.warning("Can't find 'specs' document in 'heatmap' collection. Creating a new one.")
        initial_specs = {
            "gravel": {"main_blob_name": "heatmap/gravel_v00.gpx", "compose_count": 0, "version": 0},
            "mtb": {"main_blob_name": "heatmap/mtb_v00.gpx", "compose_count": 0, "version": 0},
            "unknown": {"main_blob_name": "heatmap/unknown_v00.gpx", "compose_count": 0, "version": 0},
        }
        specs_ref.set(initial_specs)
        state = initial_specs.get(gpx_name)

    main_blob_name = state["main_blob_name"]
    compose_count = state["compose_count"]
    version = state["version"]

    # Loading index from Firestore
    index_ref = db.collection('heatmap').document(index_doc_name)
    index_doc = index_ref.get()
    indexed_dates = set()
    if index_doc.exists:
        index_data = index_doc.to_dict()
        indexed_dates = set(index_data.get('dates', []))


    # Extract date
    first_date = extract_first_time_tag(local_gpx)
    if not first_date:
        logger.warning(f"File '{local_gpx}' not include tag time.")
        return

    if first_date in indexed_dates:
        logger.warning(f"Date {first_date} already in the index. File not added.")
        return

    strip_source_content(local_gpx)

    # Loaded fragment to bucket
    fragment_blob_name = f"heatmap/fragments/{os.path.basename(local_gpx)}"
    upload_to_gcp_bucket(bucket_name, fragment_blob_name, local_gpx, "filename")

    # Union
    fragment_blob = bucket.blob(fragment_blob_name)
    if not fragment_blob.exists():
        logger.error(f"Error: Fragment '{fragment_blob_name}' doesn't exist.")
        return

    main_blob = bucket.blob(main_blob_name)
    if not main_blob.exists():
        logger.warning(f"Heatmap file doesn't exist. Creating empty blob with XML header. His compose version is 0")
        main_blob_path = os.path.join(LOCAL_TMP, os.path.basename(main_blob_name))
        os.makedirs(os.path.dirname(main_blob_path), exist_ok=True)
        with open(main_blob_path, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0" encoding="UTF-8"?>
        <gpx version="1.1" creator="SPipeline">
         """)
        upload_to_gcp_bucket(bucket_name, main_blob_name, main_blob_path, "filename")
        logger.debug(f"Heatmap created for '{gpx_name.upper()}' bike.")

    main_blob.compose([main_blob, fragment_blob])
    compose_count += 1
    logger.debug(f"Fragment '{fragment_blob_name}' added to '{main_blob_name}'.")

    # If the limit is reached - create a new version
    if compose_count >= max_compose:
        version += 1
        new_main_blob_name = f"heatmap/{gpx_name}_v{version:02d}.gpx"
        # Only one compose operation remained, we used it to create a successor
        bucket.blob(new_main_blob_name).compose([main_blob])

        try:
            delete_blob(bucket_name, main_blob_name)
            logger.info(f"Previous version '{main_blob_name}' deleted.")
        except Exception as e:
            logger.error(f"Unable to delete {main_blob_name}: {e}")

        main_blob_name = new_main_blob_name
        compose_count = 1  # the first composition already gone
        logger.info(f"Create new version: '{main_blob_name}'")

    # Update state in Firestore
    state = {
        "main_blob_name": main_blob_name,
        "compose_count": compose_count,
        "version": version
    }
    specs_ref.update({f'{gpx_name}': state})
    logger.debug(f"State updated in Firestore: compose_count={compose_count}, version={version}")

    # Update index in Firestore
    index_ref.set({'dates': firestore.ArrayUnion([first_date])}, merge=True)
    logger.debug("Index activities updated in Firestore.")

    # Delete fragment
    delete_blob(bucket_name, fragment_blob_name)

    # Delete GPX from the bucket. But I need a single file for GIS analyze later. So, it will be deleted after this analyze (coming soon...)
    # delete_blob(bucket_name, gpx_gcs_path)
    # logger.info(f"GPX '{gpx_gcs_path}' deleting after union.")
