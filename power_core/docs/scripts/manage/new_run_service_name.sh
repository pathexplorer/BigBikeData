#!/bin/bash
#
## ATTENTION: script delete tag from results, so it dont use for backup policy,
#
#
#read -p "Enter OLD service name: " raw_input
#read -p "Enter NEW service name: " new_raw_input
## Configuration
#OLD_SERVICE=$raw_input
#NEW_SERVICE=$new_raw_input
#BACKUP_FILE="policy-backup.yaml"
#
#echo "--- 1. Checking IAM Policy for $OLD_SERVICE ---"
#
## Export the current policy to a file
#gcloud run services get-iam-policy $OLD_SERVICE \
#  --region $REGION \
#  --format=yaml > $BACKUP_FILE
#
#sed -i '/^etag:/d' $BACKUP_FILE
#echo "✅ Policy saved to $BACKUP_FILE"
#echo "Here is the content of the backup:"
#cat $BACKUP_FILE
#
#echo -e "\n--- 2. Instructions to Apply to New Service ---"
#echo "After you deploy '$NEW_SERVICE', you can apply this policy using:"
#echo "gcloud run services set-iam-policy $NEW_SERVICE $BACKUP_FILE --region $REGION"
#
## Optional: Automatic restoration logic (commented out for safety)
# read -p "Do you want to apply this policy to $NEW_SERVICE now? (y/n) " -n 1 -r
# echo
# if [[ $REPLY =~ ^[Yy]$ ]]; then
#    gcloud run services set-iam-policy $NEW_SERVICE $BACKUP_FILE --region $REGION
#    echo "✅ Policy applied to $NEW_SERVICE"
# fi
#
#

