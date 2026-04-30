# AWS App Runner deployment (experimental)

> Status: experimental. Primary deploy target is HF Spaces (see root `README.md`). This folder exists so we can A/B against AWS without touching the main path.

## Why App Runner

Single-container, HTTPS + autoscaling out of the box, no VPC/ALB/task-definition ceremony. Closest AWS analogue to HF Spaces for a Gradio app.

## Layout

```
deploy/aws-apprunner/
├── Dockerfile               # uv-based, two-stage, runs `python app.py` on :7860
├── .dockerignore
└── terraform/
    ├── versions.tf          # provider pin
    ├── variables.tf
    ├── main.tf              # ECR repo, IAM roles, autoscaling config, App Runner service
    ├── outputs.tf
    ├── terraform.tfvars.example
    └── .gitignore
```

Everything AWS-side is Terraform-managed: ECR repo, both IAM roles (ECR-access + instance), the single-instance auto-scaling config, and the service itself. Image build/push is the only step that stays imperative — Terraform doesn't build Docker images.

## One-time prerequisites

**Secrets in Secrets Manager** — values stay outside Terraform state, referenced by `data` lookups:

```bash
aws secretsmanager create-secret --name meridian/openai-api-key      --secret-string "sk-..."
aws secretsmanager create-secret --name meridian/mcp-server-url      --secret-string "https://..."
aws secretsmanager create-secret --name meridian/langfuse-public-key --secret-string "pk-lf-..."
aws secretsmanager create-secret --name meridian/langfuse-secret-key --secret-string "sk-lf-..."
```

If you pick different names, override the `secret_name_*` vars.

## Deploy

```bash
cd deploy/aws-apprunner/terraform
cp terraform.tfvars.example terraform.tfvars   # edit region

# 1. Create the ECR repo + IAM roles + (empty) service skeleton
terraform init
terraform apply -target=aws_ecr_repository.bot \
                -target=aws_iam_role.ecr_access \
                -target=aws_iam_role.instance \
                -target=aws_iam_role_policy.secrets_read \
                -target=aws_iam_role_policy_attachment.ecr_access \
                -target=aws_apprunner_auto_scaling_configuration_version.single

# 2. Build & push the image (App Runner needs the image to exist before service create)
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REGION=$(terraform output -raw -json 2>/dev/null | jq -r '.region.value // empty' || echo us-east-1)
REPO=$(terraform output -raw ecr_repository_url)
TAG=$(git rev-parse --short HEAD)

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
docker build -f ../Dockerfile -t "$REPO:$TAG" ../../..
docker push "$REPO:$TAG"

# 3. Apply with the real image tag — creates the service
terraform apply -var "image_tag=$TAG"

terraform output service_url
```

## Subsequent deploys

```bash
TAG=$(git rev-parse --short HEAD)
docker build -f ../Dockerfile -t "$REPO:$TAG" ../../..
docker push "$REPO:$TAG"
terraform apply -var "image_tag=$TAG"
```

The image-tag change makes Terraform call `update-service`. Wait ~3–5 minutes for App Runner to roll over.

## Pinned to one instance — on purpose

`MemorySaver` is in-process. If App Runner scaled out, a follow-up turn could land on a different instance and lose conversation state. `aws_apprunner_auto_scaling_configuration_version.single` pins `min=max=1`. Lift this only after the session store moves to Redis/Postgres (production gap #1 in `CLAUDE.md`).

## State

Local `terraform.tfstate` is fine for an experimental footprint. Move to an S3 + DynamoDB backend before a second person touches this.

## Cost shape

App Runner bills CPU + memory provisioned (always-on at min-size 1) plus per-request. At `1 vCPU / 2 GB` always-on, expect ~\$45–55/month before traffic. HF Spaces free tier is \$0. Drop `cpu=512` / `memory=1024` for a quieter demo if it fits.

## Teardown

```bash
terraform destroy
```

Secrets in Secrets Manager are not Terraform-managed and survive `destroy`. Delete them by hand if you really want them gone (they're soft-deleted with a 7-day window).
