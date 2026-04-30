# AWS App Runner deployment

> Primary deploy target. Single-container, HTTPS + autoscaling, secrets wired via Terraform variables.

## Why App Runner

Single-container, HTTPS + autoscaling out of the box, no VPC/ALB/task-definition ceremony. Closest AWS analogue to HF Spaces for a Gradio app.

## Layout

```
deploy/aws-apprunner/
├── Dockerfile               # uv-based, two-stage, runs `python app.py` on :7860
├── .dockerignore
├── build.sh                 # zip → S3 → CodeBuild → wait
└── terraform/
    ├── versions.tf          # provider pins (aws, random)
    ├── variables.tf
    ├── main.tf              # ECR repo, App Runner IAM roles, autoscaling, App Runner service
    ├── codebuild.tf         # S3 source bucket, CodeBuild IAM, CodeBuild project
    ├── outputs.tf
    ├── terraform.tfvars.example
    └── .gitignore
```

Everything AWS-side is Terraform-managed — ECR, both App Runner IAM roles, the single-instance autoscaling config, the App Runner service, the S3 source bucket, and the CodeBuild project. The image build itself runs inside AWS via CodeBuild, so there's no local Docker step. `build.sh` is a thin wrapper that zips the working tree, uploads to S3, calls `aws codebuild start-build`, and polls until the build finishes.

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

Three phases — Terraform can't create the App Runner service before its image exists in ECR, so the build runs between two applies.

```bash
cd deploy/aws-apprunner/terraform
cp terraform.tfvars.example terraform.tfvars   # edit region
terraform init

# Phase 1: AWS skeleton (ECR, App Runner IAM, autoscaling, S3 source bucket, CodeBuild)
terraform apply \
  -target=aws_ecr_repository.bot \
  -target=aws_iam_role.ecr_access \
  -target=aws_iam_role.instance \
  -target=aws_iam_role_policy.secrets_read \
  -target=aws_iam_role_policy_attachment.ecr_access \
  -target=aws_apprunner_auto_scaling_configuration_version.single \
  -target=random_id.source_suffix \
  -target=aws_s3_bucket.source \
  -target=aws_s3_bucket_public_access_block.source \
  -target=aws_s3_bucket_server_side_encryption_configuration.source \
  -target=aws_iam_role.codebuild \
  -target=aws_iam_role_policy.codebuild \
  -target=aws_codebuild_project.build

# Phase 2: build & push (runs in AWS, ~80s end-to-end)
../build.sh

# Phase 3: create the App Runner service using the tag build.sh just printed
terraform apply -var "image_tag=<tag-from-build.sh-output>"
terraform output service_url
```

`build.sh` packages tracked + untracked-not-ignored files (`git ls-files --cached --others --exclude-standard`), so iteration works without forcing a commit. Override the tag with `IMAGE_TAG=foo ../build.sh` if you don't want the git short-SHA default.

## Subsequent deploys

```bash
../build.sh
terraform apply -var "image_tag=$(git rev-parse --short HEAD)"
```

The image-tag change makes Terraform call `update-service`. Build is ~80s in CodeBuild; App Runner's rolling deploy is another ~3 min before traffic hits the new version.

## Pinned to one instance — on purpose

`MemorySaver` is in-process. If App Runner scaled out, a follow-up turn could land on a different instance and lose conversation state. `aws_apprunner_auto_scaling_configuration_version.single` pins `min=max=1`. Lift this only after the session store moves to Redis/Postgres (production gap #1 in `CLAUDE.md`).

## State

Local `terraform.tfstate` is fine for an experimental footprint. Move to an S3 + DynamoDB backend before a second person touches this.

## Cost shape

App Runner bills CPU + memory provisioned (always-on at min-size 1) plus per-request. At `1 vCPU / 2 GB` always-on, expect ~\$45–55/month before traffic. Drop `cpu=512` / `memory=1024` for a quieter demo if it fits. CodeBuild on `BUILD_GENERAL1_SMALL` is ~\$0.005/min — each build is fractions of a cent. The S3 source bucket and ECR storage are negligible.

## Teardown

```bash
terraform destroy
```

Secrets in Secrets Manager are not Terraform-managed and survive `destroy`. Delete them by hand if you really want them gone (they're soft-deleted with a 7-day window). The S3 source bucket has `force_destroy = true`, so `terraform destroy` removes it even with `source.zip` inside.
