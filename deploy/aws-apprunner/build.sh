#!/usr/bin/env bash
# Zip the working tree, upload to S3, run CodeBuild, wait for it to finish.
# Prints the image tag on success — feed it to `terraform apply -var "image_tag=$TAG"`.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TF_DIR="$HERE/terraform"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

REGION="$(terraform -chdir="$TF_DIR" output -raw region 2>/dev/null || echo us-east-1)"
BUCKET="$(terraform -chdir="$TF_DIR" output -raw source_bucket)"
PROJECT="$(terraform -chdir="$TF_DIR" output -raw codebuild_project)"
TAG="${IMAGE_TAG:-$(git -C "$REPO_ROOT" rev-parse --short HEAD)}"

ZIP="$(mktemp -t source.XXXXXX.zip)"
trap 'rm -f "$ZIP"' EXIT

echo "==> Packaging working tree → $ZIP"
rm -f "$ZIP"
( cd "$REPO_ROOT" && git ls-files --cached --others --exclude-standard -z \
    | xargs -0 zip -q "$ZIP" )

echo "==> Uploading to s3://$BUCKET/source.zip"
aws s3 cp "$ZIP" "s3://$BUCKET/source.zip" --region "$REGION" >/dev/null

echo "==> Starting CodeBuild ($PROJECT) with IMAGE_TAG=$TAG"
BUILD_ID="$(aws codebuild start-build \
  --region "$REGION" \
  --project-name "$PROJECT" \
  --environment-variables-override "name=IMAGE_TAG,value=$TAG,type=PLAINTEXT" \
  --query 'build.id' --output text)"
echo "    build id: $BUILD_ID"
echo "    logs:     https://${REGION}.console.aws.amazon.com/codesuite/codebuild/projects/${PROJECT}/build/${BUILD_ID//:/%3A}"

echo "==> Waiting for build to finish"
while :; do
  STATUS="$(aws codebuild batch-get-builds --region "$REGION" --ids "$BUILD_ID" \
    --query 'builds[0].buildStatus' --output text)"
  case "$STATUS" in
    SUCCEEDED) echo "    SUCCEEDED"; break ;;
    IN_PROGRESS) printf '.'; sleep 10 ;;
    *) echo; echo "    build ended with status: $STATUS"; exit 1 ;;
  esac
done

echo
echo "Image: $(terraform -chdir="$TF_DIR" output -raw ecr_repository_url):$TAG"
echo "Next: terraform -chdir=$TF_DIR apply -var 'image_tag=$TAG'"
