variable "project_name" {
  description = "Stable application identifier used for resource names and tags."
  type        = string
  default     = "eay-platform"
}

variable "environment" {
  description = "Deployment environment. Production infrastructure is intentionally separate from staging."
  type        = string
  default     = "production"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "aws_region" {
  description = "Primary AWS region. Issue #192 defines Frankfurt as canonical."
  type        = string
  default     = "eu-central-1"
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR."
  default     = "10.42.0.0/16"
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "Two public subnets for the ALB and NAT gateways."
  default     = ["10.42.0.0/24", "10.42.1.0/24"]

  validation {
    condition     = length(var.public_subnet_cidrs) == 2
    error_message = "Exactly two public subnet CIDRs are required."
  }
}

variable "app_subnet_cidrs" {
  type        = list(string)
  description = "Two private application subnets for ECS/Fargate workloads."
  default     = ["10.42.10.0/24", "10.42.11.0/24"]

  validation {
    condition     = length(var.app_subnet_cidrs) == 2
    error_message = "Exactly two application subnet CIDRs are required."
  }
}

variable "data_subnet_cidrs" {
  type        = list(string)
  description = "Two isolated data subnets for RDS and ElastiCache."
  default     = ["10.42.20.0/24", "10.42.21.0/24"]

  validation {
    condition     = length(var.data_subnet_cidrs) == 2
    error_message = "Exactly two data subnet CIDRs are required."
  }
}

variable "edge_ipv4_cidrs" {
  type        = list(string)
  description = "IPv4 CIDRs permitted to reach the origin ALB on 443. Keep empty until the authoritative edge ranges are supplied."
  default     = []
}

variable "edge_ipv6_cidrs" {
  type        = list(string)
  description = "IPv6 CIDRs permitted to reach the origin ALB on 443. Keep empty until the authoritative edge ranges are supplied."
  default     = []
}

variable "origin_certificate_arn" {
  type        = string
  description = "ACM certificate ARN for the Cloudflare-to-origin TLS listener. Empty means no listener is activated."
  default     = ""
}

variable "db_instance_class" {
  type        = string
  description = "RDS instance class."
  default     = "db.t4g.medium"
}

variable "db_allocated_storage_gib" {
  type        = number
  description = "Initial RDS gp3 storage in GiB."
  default     = 100
}

variable "db_max_allocated_storage_gib" {
  type        = number
  description = "RDS storage autoscaling ceiling in GiB."
  default     = 1000
}

variable "redis_node_type" {
  type        = string
  description = "ElastiCache node type."
  default     = "cache.t4g.small"
}

variable "evidence_bucket_name" {
  type        = string
  description = "Globally unique S3 bucket name for private evidence. Required at plan/apply time."
}

variable "backup_bucket_name" {
  type        = string
  description = "Globally unique S3 bucket name for application backup/export artifacts. Required at plan/apply time."
}

variable "deletion_protection" {
  type        = bool
  description = "Protect stateful production resources from ordinary Terraform deletion."
  default     = true
}

variable "log_retention_days" {
  type        = number
  description = "Application CloudWatch log retention."
  default     = 90
}
