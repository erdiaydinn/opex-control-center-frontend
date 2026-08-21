output "vpc_id" {
  value       = aws_vpc.main.id
  description = "Production VPC ID."
}

output "public_subnet_ids" {
  value       = aws_subnet.public[*].id
  description = "Public edge subnet IDs."
}

output "app_subnet_ids" {
  value       = aws_subnet.app[*].id
  description = "Private ECS application subnet IDs."
}

output "data_subnet_ids" {
  value       = aws_subnet.data[*].id
  description = "Isolated RDS/Valkey subnet IDs."
}

output "origin_alb_dns_name" {
  value       = aws_lb.origin.dns_name
  description = "Cloudflare origin target. The security group remains closed until authoritative edge CIDRs are provided."
}

output "ecs_cluster_arn" {
  value       = aws_ecs_cluster.main.arn
  description = "EAY ECS/Fargate cluster ARN."
}

output "service_discovery_namespace_id" {
  value       = aws_service_discovery_private_dns_namespace.services.id
  description = "Private ECS service-discovery namespace."
}

output "ecr_repository_urls" {
  value       = { for name, repo in aws_ecr_repository.service : name => repo.repository_url }
  description = "Immutable ECR repositories for deployable EAY services."
}

output "rds_endpoint" {
  value       = aws_db_instance.postgres.address
  description = "Private RDS hostname."
}

output "rds_master_secret_arn" {
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
  description = "AWS-managed bootstrap/admin database secret. Runtime services must not use this identity."
  sensitive   = true
}

output "redis_primary_endpoint" {
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
  description = "Private Valkey/Redis primary endpoint."
}

output "redis_auth_secret_arn" {
  value       = aws_secretsmanager_secret.redis_auth.arn
  description = "Managed Valkey auth-token secret ARN."
  sensitive   = true
}

output "application_secret_arns" {
  value       = { for name, secret in aws_secretsmanager_secret.application : name => secret.arn }
  description = "Secret containers. Terraform intentionally does not populate application secret values."
}

output "evidence_bucket_arn" {
  value       = aws_s3_bucket.evidence.arn
  description = "Private versioned Object-Lock-capable evidence bucket ARN."
}

output "backup_bucket_arn" {
  value       = aws_s3_bucket.backup.arn
  description = "Private versioned backup/export bucket ARN."
}

output "platform_kms_key_arn" {
  value       = aws_kms_key.platform.arn
  description = "EAY application/data KMS key ARN."
}
