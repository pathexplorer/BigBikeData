remove_the_token_creator_role() {
  local sa_email1=$1
  local sa_email2=$2
  local my_user_account=$3

  gcloud iam service-accounts remove-iam-policy-binding "$sa_email1" \
      --member="user:$my_user_account" \
      --role="roles/iam.serviceAccountTokenCreator"
  echo "Removed grant the Token Creator Role from $sa_email1"
  gcloud iam service-accounts remove-iam-policy-binding "$sa_email2" \
      --member="user:$my_user_account" \
      --role="roles/iam.serviceAccountTokenCreator"
  echo "Removed grant the Token Creator Role from $sa_email2"
}