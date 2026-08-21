locals {
  ecr_repositories = toset([
    "frontend",
    "gateway",
    "core-api",
    "identity-gateway",
    "platform-alerts",
    "worker"
  ])

  secret_names = toset([
    "runtime-database-url",
    "migration-database-url",
    "identity-gateway-signing-key",
    "internal-assertion-jwks",
    "alert-oidc-client-secret"
  ])
}

resource "aws_ecr_repository" "service" {
  for_each = local.ecr_repositories

  name                 = "${local.name}/${each.value}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "KMS"
    kms_key         = aws_kms_key.platform.arn
  }

  tags = {
    Name    = "${local.name}-${each.value}"
    Service = each.value
  }
}

resource "aws_ecr_lifecycle_policy" "service" {
  for_each   = aws_ecr_repository.service
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Retain the newest 50 immutable images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 50
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

resource "aws_ecs_cluster" "main" {
  name = "${local.name}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name = "${local.name}-cluster"
  }
}

resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name = aws_ecs_cluster.main.name

  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    base              = 1
    weight            = 1
  }
}

resource "aws_service_discovery_private_dns_namespace" "services" {
  name        = "eay.internal"
  description = "Private service discovery for EAY ECS workloads"
  vpc         = aws_vpc.main.id
}

resource "aws_lb" "origin" {
  name                       = substr(replace("${local.name}-origin", "_", "-"), 0, 32)
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = aws_subnet.public[*].id
  drop_invalid_header_fields = true
  enable_deletion_protection = var.deletion_protection

  tags = {
    Name       = "${local.name}-origin"
    Exposure   = "edge-restricted"
    Activation = "fail-closed"
  }
}

resource "aws_lb_listener" "https_hold" {
  count = var.origin_certificate_arn == "" ? 0 : 1

  load_balancer_arn = aws_lb.origin.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.origin_certificate_arn

  default_action {
    type = "fixed-response"

    fixed_response {
      content_type = "application/json"
      message_body = "{\"status\":\"hold\",\"reason\":\"production_workload_not_activated\"}"
      status_code  = "503"
    }
  }

  tags = {
    Activation = "hold-until-exact-release"
  }
}

data "aws_iam_policy_document" "ecs_task_execution_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${local.name}-ecs-task-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_assume.json

  tags = {
    Name = "${local.name}-ecs-task-execution"
  }
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_secretsmanager_secret" "application" {
  for_each = local.secret_names

  name                    = "${local.name}/${each.value}"
  kms_key_id              = aws_kms_key.platform.arn
  recovery_window_in_days = 30

  tags = {
    Name       = "${local.name}-${each.value}"
    Populated  = "false-by-terraform"
    SecretType = each.value
  }
}

data "aws_iam_policy_document" "ecs_task_execution_secrets" {
  statement {
    sid    = "ReadNamedEaySecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue"
    ]
    resources = concat(
      [for secret in aws_secretsmanager_secret.application : secret.arn],
      [aws_secretsmanager_secret.redis_auth.arn],
      [aws_db_instance.postgres.master_user_secret[0].secret_arn]
    )
  }

  statement {
    sid    = "DecryptEaySecrets"
    effect = "Allow"
    actions = [
      "kms:Decrypt"
    ]
    resources = [aws_kms_key.platform.arn]
  }
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name   = "${local.name}-secret-injection"
  role   = aws_iam_role.ecs_task_execution.id
  policy = data.aws_iam_policy_document.ecs_task_execution_secrets.json
}
