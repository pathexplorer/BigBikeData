from gcp_actions.client import get_bucket


bucket = get_bucket("GCS_BUCKET_NAME")
print(bucket)


#Connect to bucket
for blob in bucket.list_blobs():
   print("Files in bucket:", blob.name)

def list_gcs_files(bucket_name, prefix):
    blobs = bucket.list_blobs(prefix=prefix)
    print("Blobs", blobs)
    print("Pref", prefix)
    return [f'gs://{bucket_name}/{blob.name}' for blob in blobs]

# rez = list_gcs_files(config.GCS_BUCKET_NAME, config.GSC_ORIG_FIT_FOLDER)
# local_fit = "D:/111/tt.txt"
# with open(local_fit, "w") as f:  # Save locally for java app (for loading from file, instead load from bites)
#     f.write('gs://wahoobucket/dropbox_sync/apps/activities/20.txt')
#
# print(rez)
# print(type(rez))
