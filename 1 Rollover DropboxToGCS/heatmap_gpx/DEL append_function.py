import os
import re
from google.cloud import storage
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")

GPX_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd http://www.garmin.com/xmlschemas/GpxExtensions/v3 http://www.garmin.com/xmlschemas/GpxExtensionsv3.xsd http://www.garmin.com/xmlschemas/TrackPointExtension/v1 http://www.garmin.com/xmlschemas/TrackPointExtensionv1.xsd" creator="StravaGPX" version="1.1" xmlns="http://www.topografix.com/GPX/1/1" xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1" xmlns:gpxx="http://www.garmin.com/xmlschemas/GpxExtensions/v3">
"""



HEATMAP_INDEX_PATH = f'heatmap/'
def download_index_from_gcs(blob_path, local_path):
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(blob_path)
    blob.download_to_filename(local_path)






def extract_first_time_tag(file_path: str) -> str | None:
    time_pattern = re.compile(r"<time>(.*?)</time>")
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = time_pattern.search(line)
            if match:
                return match.group(1)
    return None

def ensure_gpx_header(target_file: str):
    if not os.path.exists(target_file):
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(GPX_HEADER + "\n")

def strip_source_content(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if len(lines) <= 2:
        return ""  # недостатньо рядків для обрізання
    return "".join(lines[2:])  # видаляємо лише перші дві строки

def remove_last_line(file_path: str):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if len(lines) < 1:
        return
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines[:-1])  # записуємо все крім останньої строки

 
def append_gpx_with_index(source_file: str, bike_model: str):
    def chose_branch(model):
        if model == 'b7647614':
            rez = ['/tmp/mtb.gpx', '/tmp/mtb_index.txt']
            return rez
        elif model == 'b8850168':
            rez = ['/tmp/gravel.gpx', '/tmp/gravel_index.txt']
            return rez
        return None

    branch = chose_branch(bike_model)
    if branch is None:

        print(f"Невідомий bike_model: {bike_model}")
        return

    target_file, index_file = branch



    ensure_gpx_header(target_file)

    if not os.path.exists(index_file):
        open(index_file, "w", encoding="utf-8").close()

    first_date = extract_first_time_tag(source_file)
    if not first_date:
        print(f"У файлі '{source_file}' не знайдено тег <time>.")
        return

    with open(index_file, "r", encoding="utf-8") as idx:
        indexed_dates = set(line.strip() for line in idx)

    if first_date in indexed_dates:
        print(f"Дата {first_date} вже є в індексі. Файл не буде додано.")
        return

    with open(index_file, "a", encoding="utf-8") as idx:
        idx.write(first_date + "\n")

    stripped_content = strip_source_content(source_file)
    if not stripped_content:
        print(f"Файл '{source_file}' не має достатньо рядків для обрізання.")
        return

    remove_last_line(target_file)

    with open(target_file, "a", encoding="utf-8") as tgt:
        tgt.write(stripped_content)

    print(f"Файл '{source_file}' додано до '{target_file}', дата {first_date} записана в індекс.")
