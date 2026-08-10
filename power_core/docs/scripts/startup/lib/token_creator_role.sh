remove_the_token_creator_role() {
  local sa_email1=$1
  local sa_email2=$2
  local my_user_account=$3

  if [[ "${DRY_RUN:-false}" == "true" ]]; then
      echo "🔍 [DRY-RUN] Would remove Token Creator role from $sa_email1 for user $my_user_account"
      echo "🔍 [DRY-RUN] Would remove Token Creator role from $sa_email2 for user $my_user_account"
      return 0
  fi

  run_cmd gcloud iam service-accounts remove-iam-policy-binding "$sa_email1" \
      --member="user:$my_user_account" \
      --role="roles/iam.serviceAccountTokenCreator"
  echo "Removed grant the Token Creator Role from $sa_email1"
  run_cmd gcloud iam service-accounts remove-iam-policy-binding "$sa_email2" \
      --member="user:$my_user_account" \
      --role="roles/iam.serviceAccountTokenCreator"
  echo "Removed grant the Token Creator Role from $sa_email2"
}