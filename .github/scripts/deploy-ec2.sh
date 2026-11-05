#!/usr/bin/env bash
# Deploy an image to the EC2 host through SSM Run Command (no SSH) and wait for the result.
#
# On the host it: writes docker-compose.prod.yaml and .env (DB password from SSM Parameter Store),
# pulls the image from ECR, starts Postgres, runs `alembic upgrade head`, starts the app and
# checks /health.
#
# Usage: deploy-ec2.sh <instance-id> <image-uri>
# Env:   AWS_REGION (required), SSM_PARAMETER_PREFIX (default /project-manager)
set -euo pipefail

instance_id=$1
image=$2
region=${AWS_REGION:?AWS_REGION must be set}
registry=${image%%/*}
param_prefix=${SSM_PARAMETER_PREFIX:-/project-manager}
compose_b64=$(base64 -w0 docker-compose.prod.yaml)

remote_script=$(cat <<REMOTE
set -eu
mkdir -p /opt/project-manager
cd /opt/project-manager
echo '$compose_b64' | base64 -d > docker-compose.prod.yaml
db_password=\$(aws ssm get-parameter --region $region --name $param_prefix/postgres-password --with-decryption --query Parameter.Value --output text)
umask 077
printf 'APP_IMAGE=%s\nPOSTGRES_PASSWORD=%s\n' '$image' "\$db_password" > .env
aws ecr get-login-password --region $region | docker login --username AWS --password-stdin $registry
docker compose -f docker-compose.prod.yaml pull app
docker compose -f docker-compose.prod.yaml up -d --wait db
docker compose -f docker-compose.prod.yaml run --rm app alembic upgrade head
docker compose -f docker-compose.prod.yaml up -d --remove-orphans
docker image prune -f
for attempt in \$(seq 1 30); do curl -fsS http://localhost/health && echo && exit 0; sleep 2; done
echo "Health check failed"; docker compose -f docker-compose.prod.yaml logs --tail 50 app; exit 1
REMOTE
)

params=$(jq -n --arg script "$remote_script" '{commands: ($script | split("\n"))}')
command_id=$(aws ssm send-command \
  --instance-ids "$instance_id" \
  --document-name AWS-RunShellScript \
  --comment "deploy ${GITHUB_SHA:-manual}" \
  --timeout-seconds 600 \
  --parameters "$params" \
  --query Command.CommandId --output text)
echo "SSM command: $command_id"

status=Pending
for _ in $(seq 1 120); do
  sleep 5
  status=$(aws ssm get-command-invocation --command-id "$command_id" --instance-id "$instance_id" \
    --query Status --output text 2>/dev/null || echo Pending)
  case $status in Pending|InProgress|Delayed) ;; *) break ;; esac
done

echo "----- output from the instance -----"
aws ssm get-command-invocation --command-id "$command_id" --instance-id "$instance_id" \
  --query '[StandardOutputContent, StandardErrorContent]' --output text || true
echo "Deploy status: $status"
[ "$status" = "Success" ]
