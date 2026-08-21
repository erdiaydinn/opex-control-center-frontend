locals {
  log_groups = toset([
    "gateway",
    "frontend",
    "core-api",
    "identity-gateway",
    "platform-alerts",
    "worker",
    "migration"
  ])
}

resource "aws_cloudwatch_log_group" "service" {
  for_each = local.log_groups

  name              = "/eay/${var.environment}/${each.value}"
  retention_in_days = var.log_retention_days
  kms_key_id        = aws_kms_key.platform.arn

  tags = {
    Service   = each.value
    DataClass = "application-log"
  }
}

resource "aws_sns_topic" "production_alerts" {
  name              = "${local.name}-alerts"
  kms_master_key_id = aws_kms_key.platform.id

  tags = {
    Name = "${local.name}-alerts"
  }
}

resource "aws_cloudwatch_dashboard" "foundation" {
  dashboard_name = "${local.name}-foundation"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 3
        properties = {
          markdown = "# EAY Production Foundation\nThis dashboard covers infrastructure authority only. Application workload activation remains fail-closed until an exact release SHA/image digest is admitted."
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 3
        width  = 12
        height = 6
        properties = {
          region = var.aws_region
          title  = "RDS CPU / Connections"
          metrics = [
            ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", aws_db_instance.postgres.identifier],
            [".", "DatabaseConnections", ".", "."]
          ]
          period = 300
          stat   = "Average"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 3
        width  = 12
        height = 6
        properties = {
          region = var.aws_region
          title  = "ALB 5xx / Request Count"
          metrics = [
            ["AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", "LoadBalancer", aws_lb.origin.arn_suffix],
            [".", "RequestCount", ".", "."]
          ]
          period = 300
          stat   = "Sum"
        }
      }
    ]
  })
}
