#!/bin/bash
echo "Log history showed: $CLOUD_RUN_SERVICE"
#gcloud alpha logging tail \
#  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$CLOUD_RUN_SERVICE\" AND logName!=\"projects/$GCP_PROJECT_ID/logs/run.googleapis.com%2Frequests\"" \
#   --format="value(jsonPayload.message)"
#   --format="value(jsonPayload.message, jsonPayload.filename, jsonPayload.lineno)"


GCP_FILTER="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$CLOUD_RUN_SERVICE\" AND (
  severity >= WARNING OR (
    severity = INFO AND (
      NOT jsonPayload.filename : \"/usr/local/lib/python3.12/site-packages/\" AND
      NOT jsonPayload.filename : \"dropbox_client.py\"
    )
  )
)"

gcloud logging read "$GCP_FILTER" \
  --limit=200 \
  --freshness="20m" \
  --format="table[no-heading,no-wrap](
      timestamp.date(format='%H:%M:%S', tz='LOCAL'),
      severity,
      firstof(jsonPayload.message, textPayload),
      jsonPayload.filename,
      jsonPayload.lineno
  )"\
  | tac # revert order of lines in classic log style - newer message at the bottom. Use for quick check-up result of service