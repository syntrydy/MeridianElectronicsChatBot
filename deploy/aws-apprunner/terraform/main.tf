data "aws_caller_identity" "current" {}

locals {
  image_uri = "${aws_ecr_repository.bot.repository_url}:${var.image_tag}"
}

resource "aws_ecr_repository" "bot" {
  name                 = var.service_name
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Pre-existing secrets — values managed out of band so they never enter Terraform state.
data "aws_secretsmanager_secret" "openai_api_key" {
  name = var.secret_name_openai_api_key
}

data "aws_secretsmanager_secret" "mcp_server_url" {
  name = var.secret_name_mcp_server_url
}

data "aws_secretsmanager_secret" "langfuse_public_key" {
  name = var.secret_name_langfuse_public_key
}

data "aws_secretsmanager_secret" "langfuse_secret_key" {
  name = var.secret_name_langfuse_secret_key
}

resource "aws_iam_role" "ecr_access" {
  name = "${var.service_name}-apprunner-ecr"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "build.apprunner.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ecr_access" {
  role       = aws_iam_role.ecr_access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

resource "aws_iam_role" "instance" {
  name = "${var.service_name}-apprunner-instance"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "tasks.apprunner.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "secrets_read" {
  name = "${var.service_name}-secrets-read"
  role = aws_iam_role.instance.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["secretsmanager:GetSecretValue"]
      Resource = [
        data.aws_secretsmanager_secret.openai_api_key.arn,
        data.aws_secretsmanager_secret.mcp_server_url.arn,
        data.aws_secretsmanager_secret.langfuse_public_key.arn,
        data.aws_secretsmanager_secret.langfuse_secret_key.arn,
      ]
    }]
  })
}

# Pinned to one instance: MemorySaver is in-process; scale-out would drop sessions.
resource "aws_apprunner_auto_scaling_configuration_version" "single" {
  auto_scaling_configuration_name = "${var.service_name}-single"
  max_concurrency                 = 100
  min_size                        = 1
  max_size                        = 1
}

resource "aws_apprunner_service" "bot" {
  service_name = var.service_name

  source_configuration {
    auto_deployments_enabled = false

    authentication_configuration {
      access_role_arn = aws_iam_role.ecr_access.arn
    }

    image_repository {
      image_repository_type = "ECR"
      image_identifier      = local.image_uri

      image_configuration {
        port = "7860"

        runtime_environment_variables = {
          OPENAI_MODEL        = var.openai_model
          MCP_REQUEST_TIMEOUT = "30"
          LANGFUSE_HOST       = var.langfuse_host
          LOG_LEVEL           = var.log_level
          ENVIRONMENT         = var.environment
        }

        runtime_environment_secrets = {
          OPENAI_API_KEY      = data.aws_secretsmanager_secret.openai_api_key.arn
          MCP_SERVER_URL      = data.aws_secretsmanager_secret.mcp_server_url.arn
          LANGFUSE_PUBLIC_KEY = data.aws_secretsmanager_secret.langfuse_public_key.arn
          LANGFUSE_SECRET_KEY = data.aws_secretsmanager_secret.langfuse_secret_key.arn
        }
      }
    }
  }

  instance_configuration {
    cpu               = var.cpu
    memory            = var.memory
    instance_role_arn = aws_iam_role.instance.arn
  }

  auto_scaling_configuration_arn = aws_apprunner_auto_scaling_configuration_version.single.arn

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 5
  }
}
