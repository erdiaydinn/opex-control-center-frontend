resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "Cloudflare/approved edge to EAY origin only"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${local.name}-alb-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "alb_https_ipv4" {
  for_each          = toset(var.edge_ipv4_cidrs)
  security_group_id = aws_security_group.alb.id
  cidr_ipv4         = each.value
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "Authoritative edge HTTPS"
}

resource "aws_vpc_security_group_ingress_rule" "alb_https_ipv6" {
  for_each          = toset(var.edge_ipv6_cidrs)
  security_group_id = aws_security_group.alb.id
  cidr_ipv6         = each.value
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "Authoritative edge HTTPS IPv6"
}

resource "aws_security_group" "ecs" {
  name        = "${local.name}-ecs"
  description = "Private EAY ECS service plane"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${local.name}-ecs-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "ecs_gateway_from_alb" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.alb.id
  from_port                    = 80
  to_port                      = 80
  ip_protocol                  = "tcp"
  description                  = "Origin ALB to gateway"
}

resource "aws_vpc_security_group_ingress_rule" "ecs_internal_http" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 80
  to_port                      = 80
  ip_protocol                  = "tcp"
  description                  = "EAY service-to-service frontend traffic"
}

resource "aws_vpc_security_group_ingress_rule" "ecs_internal_core" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
  description                  = "EAY service-to-service Core API"
}

resource "aws_vpc_security_group_ingress_rule" "ecs_internal_identity" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 8020
  to_port                      = 8020
  ip_protocol                  = "tcp"
  description                  = "EAY service-to-service Identity Gateway"
}

resource "aws_security_group" "rds" {
  name        = "${local.name}-rds"
  description = "RDS accepts PostgreSQL only from the EAY service plane"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${local.name}-rds-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "rds_from_ecs" {
  security_group_id            = aws_security_group.rds.id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "EAY runtime/migrator PostgreSQL access"
}

resource "aws_security_group" "redis" {
  name        = "${local.name}-redis"
  description = "Valkey/Redis accepts traffic only from the EAY service plane"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "${local.name}-redis-sg"
  }
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_ecs" {
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
  description                  = "EAY runtime Valkey access"
}

resource "aws_vpc_security_group_egress_rule" "alb_to_gateway" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 80
  to_port                      = 80
  ip_protocol                  = "tcp"
  description                  = "ALB to EAY gateway"
}

resource "aws_vpc_security_group_egress_rule" "ecs_https" {
  security_group_id = aws_security_group.ecs.id
  cidr_ipv4         = "0.0.0.0/0"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  description       = "TLS egress for OIDC, AWS APIs and governed external connectors"
}

resource "aws_vpc_security_group_egress_rule" "ecs_dns_udp" {
  security_group_id = aws_security_group.ecs.id
  cidr_ipv4         = var.vpc_cidr
  from_port         = 53
  to_port           = 53
  ip_protocol       = "udp"
  description       = "VPC DNS"
}

resource "aws_vpc_security_group_egress_rule" "ecs_dns_tcp" {
  security_group_id = aws_security_group.ecs.id
  cidr_ipv4         = var.vpc_cidr
  from_port         = 53
  to_port           = 53
  ip_protocol       = "tcp"
  description       = "VPC DNS fallback"
}

resource "aws_vpc_security_group_egress_rule" "ecs_to_rds" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.rds.id
  from_port                    = 5432
  to_port                      = 5432
  ip_protocol                  = "tcp"
  description                  = "PostgreSQL"
}

resource "aws_vpc_security_group_egress_rule" "ecs_to_redis" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.redis.id
  from_port                    = 6379
  to_port                      = 6379
  ip_protocol                  = "tcp"
  description                  = "Valkey"
}

resource "aws_vpc_security_group_egress_rule" "ecs_internal_http" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 80
  to_port                      = 80
  ip_protocol                  = "tcp"
  description                  = "Internal frontend/gateway traffic"
}

resource "aws_vpc_security_group_egress_rule" "ecs_internal_core" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 8000
  to_port                      = 8000
  ip_protocol                  = "tcp"
  description                  = "Internal Core API traffic"
}

resource "aws_vpc_security_group_egress_rule" "ecs_internal_identity" {
  security_group_id            = aws_security_group.ecs.id
  referenced_security_group_id = aws_security_group.ecs.id
  from_port                    = 8020
  to_port                      = 8020
  ip_protocol                  = "tcp"
  description                  = "Internal Identity Gateway traffic"
}
