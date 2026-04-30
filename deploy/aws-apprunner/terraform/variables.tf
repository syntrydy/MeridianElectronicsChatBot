variable "region" {
  type        = string
  description = "AWS region for ECR + App Runner."
}

variable "service_name" {
  type    = string
  default = "meridian-bot"
}

variable "image_tag" {
  type        = string
  description = "ECR image tag to deploy. Use a commit SHA in CI; 'latest' is fine for first apply."
  default     = "latest"
}

variable "openai_model" {
  type    = string
  default = "gpt-4o-mini"
}

variable "langfuse_host" {
  type    = string
  default = "https://cloud.langfuse.com"
}

variable "log_level" {
  type    = string
  default = "INFO"
}

variable "environment" {
  type    = string
  default = "production"
}

variable "secret_name_openai_api_key" {
  type    = string
  default = "meridian/openai-api-key"
}

variable "secret_name_mcp_server_url" {
  type    = string
  default = "meridian/mcp-server-url"
}

variable "secret_name_langfuse_public_key" {
  type    = string
  default = "meridian/langfuse-public-key"
}

variable "secret_name_langfuse_secret_key" {
  type    = string
  default = "meridian/langfuse-secret-key"
}

variable "cpu" {
  type        = string
  description = "App Runner CPU. '1024' = 1 vCPU."
  default     = "1024"
}

variable "memory" {
  type        = string
  description = "App Runner memory in MB. '2048' = 2 GB."
  default     = "2048"
}
