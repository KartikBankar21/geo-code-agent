variable "aws_region" {
  description = "AWS region for EC2 and S3"
  type        = string
  default     = "ap-south-1"
}

variable "instance_type" {
  description = "EC2 instance type for API and Execution nodes"
  type        = string
  default     = "t3.medium"
}

variable "repo_url" {
  description = "GitHub repository URL"
  type        = string
  default     = "https://github.com/KartikBankar21/geo-code-agent.git"
}

variable "repo_branch" {
  description = "Git branch to deploy"
  type        = string
  default     = "prod-aws"
}

variable "groq_api_key" {
  description = "Groq Cloud API Key"
  type        = string
  sensitive   = true
}

variable "groq_model" {
  description = "Groq model identifier"
  type        = string
  default     = "openai/gpt-oss-20b"
}

variable "qdrant_url" {
  description = "Qdrant Cloud cluster HTTPS URL"
  type        = string
}

variable "qdrant_api_key" {
  description = "Qdrant Cloud API Key"
  type        = string
  sensitive   = true
}

variable "vercel_origin" {
  description = "Vercel frontend origin for CORS (e.g., https://my-geo-agent.vercel.app)"
  type        = string
  default     = "*"
}

variable "ssh_key_name" {
  description = "Optional EC2 key pair name for SSH debugging"
  type        = string
  default     = ""
}