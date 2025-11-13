#!/bin/bash
## Cleanup (Optional)


 function cleanup {
   echo "Cleaning up resources..."
   gcloud secrets delete $SEC_DROPBOX --quiet
   gcloud secrets delete $SEC_STRAVA --quiet
   gcloud iam service-accounts delete $SA_EMAIL_1 --quiet
   gcloud iam service-accounts delete $SA_EMAIL_2 --quiet
   echo "Cleanup complete."
 }
