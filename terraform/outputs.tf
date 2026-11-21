output "api_public_ip" {
  description = "Public IP of Tier 2 API Node (paste into apps/ui/vercel.json)"
  value       = aws_instance.api_node.public_ip
}

output "api_health_url" {
  description = "Health check URL for Tier 2 API Node"
  value       = "http://${aws_instance.api_node.public_ip}:8000/api/health"
}

output "s3_artifacts_bucket" {
  description = "Provisioned S3 bucket for spatial artifacts"
  value       = aws_s3_bucket.artifacts.bucket
}