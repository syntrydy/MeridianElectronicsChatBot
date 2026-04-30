output "region" {
  value = var.region
}

output "service_url" {
  value       = "https://${aws_apprunner_service.bot.service_url}"
  description = "Public HTTPS URL of the App Runner service."
}

output "service_arn" {
  value = aws_apprunner_service.bot.arn
}

output "ecr_repository_url" {
  value       = aws_ecr_repository.bot.repository_url
  description = "Push images here, then bump var.image_tag and re-apply."
}

output "source_bucket" {
  value       = aws_s3_bucket.source.bucket
  description = "S3 bucket CodeBuild reads source.zip from."
}

output "codebuild_project" {
  value       = aws_codebuild_project.build.name
  description = "CodeBuild project name. Trigger with `aws codebuild start-build`."
}
