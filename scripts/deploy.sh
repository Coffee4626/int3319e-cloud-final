#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
stack="${STACK_NAME:-stratus-automl}"
if [[ ! "$stack" =~ ^[a-z][a-z0-9-]{2,29}$ ]]; then
  echo 'STACK_NAME must be 3–30 lowercase letters/digits/hyphens, starting with a letter.' >&2
  exit 1
fi
for cmd in aws docker node npm python3; do command -v "$cmd" >/dev/null || { echo "Missing prerequisite: $cmd" >&2; exit 1; }; done
docker info >/dev/null
aws sts get-caller-identity --query '{Account:Account,Arn:Arn}' --output table
output() {
  aws cloudformation describe-stacks --stack-name "$1" --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue | [0]" --output text
}
# Do not replace workers or inference runtimes while training deliveries are active.
if aws cloudformation describe-stacks --stack-name "$stack" >/dev/null 2>&1; then
  queue=$(output "$stack" QueueUrl)
  if [[ "$queue" != None ]]; then
    attributes=$(aws sqs get-queue-attributes --queue-url "$queue" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible ApproximateNumberOfMessagesDelayed --query Attributes --output json)
    if ! printf '%s' "$attributes" | python3 -c 'import json,sys; sys.exit(0 if sum(map(int,json.load(sys.stdin).values())) == 0 else 1)'; then
      echo 'Training queue is not empty. Let jobs finish and pause submissions before upgrading.' >&2
      exit 1
    fi
  fi
fi
if [[ -z "${VPC_ID:-}" && -z "${SUBNET_IDS:-}" ]]; then
  aws cloudformation deploy --stack-name "$stack-network" --template-file infra/network.yaml --no-fail-on-empty-changeset
  VPC_ID=$(output "$stack-network" VpcId)
  SUBNET_IDS=$(output "$stack-network" SubnetIds)
fi
: "${VPC_ID:?Set both VPC_ID and SUBNET_IDS, or leave both unset for automatic network creation}"
: "${SUBNET_IDS:?Set both VPC_ID and SUBNET_IDS, or leave both unset for automatic network creation}"
aws cloudformation deploy --stack-name "$stack-web" --template-file infra/frontend.yaml --no-fail-on-empty-changeset
origin=$(output "$stack-web" WebUrl)
aws cloudformation deploy --stack-name "$stack-registry" --template-file infra/registry.yaml --no-fail-on-empty-changeset
repo=$(output "$stack-registry" RepositoryUri)
tag="$(date -u +%Y%m%d%H%M%S)-$(git rev-parse --short HEAD 2>/dev/null || echo init)"
aws ecr get-login-password | docker login --username AWS --password-stdin "${repo%%/*}"
docker buildx build --platform linux/amd64 --provenance=false --sbom=false -t "$repo:$tag" --push .
digest=$(aws ecr describe-images --repository-name "${repo#*/}" --image-ids imageTag="$tag" --query 'imageDetails[0].imageDigest' --output text)
aws cloudformation deploy --stack-name "$stack" --template-file infra/template.yaml \
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND --no-fail-on-empty-changeset \
  --parameter-overrides "ImageUri=$repo@$digest" "VpcId=$VPC_ID" "SubnetIds=$SUBNET_IDS" \
  "AllowedOrigin=$origin" "WorkerInstanceType=${WORKER_INSTANCE_TYPE:-t3.large}" \
  "MaxWorkers=${MAX_WORKERS:-2}" "BudgetEmail=${BUDGET_EMAIL:-}"
npm --prefix frontend ci
npm --prefix frontend run build
aws cloudformation describe-stacks --stack-name "$stack" --output json | \
  python3 scripts/write_config.py --region "$AWS_DEFAULT_REGION" --output frontend/dist/config.js
bucket=$(output "$stack-web" WebBucket)
distribution=$(output "$stack-web" DistributionId)
# Keep old hashed assets available during CloudFront propagation / browser sessions.
aws s3 sync frontend/dist/ "s3://$bucket/" --exclude index.html --exclude config.js --cache-control 'public,max-age=31536000,immutable'
aws s3 cp frontend/dist/index.html "s3://$bucket/index.html" --cache-control no-cache --content-type text/html
aws s3 cp frontend/dist/config.js "s3://$bucket/config.js" --cache-control no-store --content-type application/javascript
aws cloudfront create-invalidation --distribution-id "$distribution" --paths '/*' --query Invalidation.Id --output text
aws cloudformation describe-stacks --stack-name "$stack" --query 'Stacks[0].Outputs' --output table
printf '\nFrontend: %s\nCreate a Cognito user, then sign in. See docs/aws-setup.md.\n' "$origin"
