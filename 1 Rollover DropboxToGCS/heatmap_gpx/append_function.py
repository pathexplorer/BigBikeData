from google.cloud import storage
import os
import re

BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
LOCAL_TMP = "/tmp"

def strip_source_content(file_path: str) -> str | None:
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if len(lines) <= 2:
        print("")  # недостатньо рядків для обрізання
        return None
    # Видаляємо перші два рядки та останній
    stripped_lines = lines[2:-1]
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(stripped_lines)
    return "".join(stripped_lines)




def chose_branch(bike_model):
    # Повертає локальні імена файлів
    return {
        'b7647614': ['mtb.gpx', 'mtb_index.txt'],
        'b8850168': ['gravel.gpx', 'gravel_index.txt']
    }.get(bike_model)

def extract_first_time_tag(file_path: str) -> str | None:
    time_pattern = re.compile(r"<time>(.*?)</time>")
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            match = time_pattern.search(line)
            if match:
                return match.group(1)
    return None

def download_blob_if_exists(bucket, blob_name, local_path):
    blob = bucket.blob(blob_name)
    if blob.exists():
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        blob.download_to_filename(local_path)
        return True
    return False

def upload_blob(bucket, local_path, blob_name):
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path)

def delete_blob(bucket, blob_name):
    blob = bucket.blob(blob_name)
    if blob.exists():
        blob.delete()

def append_gpx_via_compose(local_gpx: str, bike_model: str):
    branch = chose_branch(bike_model)
    if branch is None:
        print(f"Невідомий bike_model: {bike_model}")
        return

    gpx_name, index_name = branch

    # Локальні шляхи
    local_index_path = os.path.join(LOCAL_TMP, index_name)

    # Шляхи в bucket
    main_blob_name = f"heatmap/{gpx_name}"
    index_blob_name = f"heatmap/{index_name}"
    fragment_blob_name = f"heatmap/fragments/{os.path.basename(local_gpx)}"

    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)

    # Завантажити індекс
    indexed_dates = set()
    if download_blob_if_exists(bucket, index_blob_name, local_index_path):
        with open(local_index_path, "r", encoding="utf-8") as f:
            indexed_dates = set(line.strip() for line in f)

    # Витягнути дату
    first_date = extract_first_time_tag(local_gpx)
    if not first_date:
        print(f"У файлі '{local_gpx}' не знайдено тег <time>.")
        return

    if first_date in indexed_dates:
        print(f"Дата {first_date} вже є в індексі. Файл не буде додано.")
        return

    # Оновити індекс локально
    os.makedirs(os.path.dirname(local_index_path), exist_ok=True)
    with open(local_index_path, "a", encoding="utf-8") as f:
        f.write(first_date + "\n")

    strip_source_content(local_gpx)

    # Завантажити фрагмент у bucket
    upload_blob(bucket, local_gpx, fragment_blob_name)

    # Об’єднати
    main_blob = bucket.blob(main_blob_name)
    fragment_blob = bucket.blob(fragment_blob_name)

    if not main_blob.exists():
        print(f"Головний GPX-файл не існує. Створюю з шаблону.")
        main_blob_path = os.path.join(LOCAL_TMP, os.path.basename(main_blob_name))
        os.makedirs(os.path.dirname(main_blob_path), exist_ok=True)

        with open(main_blob_path, "w", encoding="utf-8") as f:
            f.write("""<?xml version="1.0" encoding="UTF-8"?>
        <gpx version="1.1" creator="SPipeline">
         """)

        upload_blob(bucket, main_blob_path, main_blob_name)
        print(f"Шаблон GPX-файлу завантажено як '{main_blob_name}'.")


    main_blob.compose([main_blob, fragment_blob])
    print(f"Файл '{fragment_blob_name}' додано до '{main_blob_name}'.")

    # # 1. Створити локальний файл з </gpx>
    # closer_path = os.path.join(LOCAL_TMP, "gpx_closer.gpx")
    # with open(closer_path, "w", encoding="utf-8") as f:
    #     f.write("</gpx>\n")
    #
    # # 2. Завантажити в bucket
    # closer_blob_name = "heatmap/closer.gpx"
    # upload_blob(bucket, closer_path, closer_blob_name)
    #
    # # 3. Об’єднати з основним GPX
    # closer_blob = bucket.blob(closer_blob_name)
    # if not closer_blob.exists():
    #     print(f"closer_blob '{closer_blob_name}' не існує — не додаємо </gpx>")
    #     return
    # print(f"closer_blob розмір: {closer_blob.size} байт")
    # main_blob.compose([main_blob, closer_blob])
    # print("Закриваючі теги додано через compose.")
    #
    # # 4. (необов’язково) Видалити closer blob
    # delete_blob(bucket, closer_blob_name)

    # Завантажити оновлений індекс назад
    upload_blob(bucket, local_index_path, index_blob_name)

    # 🧹 Видалити фрагмент
    delete_blob(bucket, fragment_blob_name)
    print(f"Фрагмент '{fragment_blob_name}' видалено після об’єднання.")
