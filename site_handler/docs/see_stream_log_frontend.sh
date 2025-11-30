#!/bin/bash
echo "History log shows: $CLOUD_RUN_SERVICE_PUB "
#gcloud alpha logging tail \
#  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$CLOUD_RUN_SERVICE_PUB\" AND logName!=\"projects/$GCP_PROJECT_ID/logs/run.googleapis.com%2Frequests\"" \
#  --format="value(jsonPayload.message)"

gcloud logging read \
  "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"$CLOUD_RUN_SERVICE_PUB\"" \
  --limit=40 \
  --freshness="80m" \
  --format="table[no-heading](
      timestamp.date(format='%H:%M:%S', tz='LOCAL'),
      severity,
      firstof(jsonPayload.message, textPayload),
      jsonPayload.filename,
      jsonPayload.lineno
  )"\
| tac # revert order of lines in classic log style - newer message at the bottom. Use for quick check-up result of service