#!/bin/bash
## Cleanup (Optional)
 function cleanup {
   echo "Cleaning up resources..."
   gcloud secrets delete "$SEC_DROPBOX" --quiet
   gcloud secrets delete "$SEC_FULLSTACK_JSON_KEYS" --quiet
   gcloud iam service-accounts delete "$SA_EMAIL_1" --quiet
   gcloud iam service-accounts delete "$SA_EMAIL_2" --quiet
   gcloud iam service-accounts delete "$SA_EMAIL_EVENTARC" --quiet
   if [[ -n "${SA_DEPLOYER_EMAIL:-}" ]]; then
       gcloud iam service-accounts delete "$SA_DEPLOYER_EMAIL" --quiet
   fi
   echo "Cleanup complete."
}
