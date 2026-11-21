terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Ubuntu 24.04 LTS AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

resource "random_id" "suffix" {
  byte_length = 4
}

resource "random_password" "executor_secret" {
  length  = 32
  special = false
}

# -------------------------------------------------------------------------
# S3 Bucket for Spatial Artifacts (force_destroy = true ensures $0 teardown)
# -------------------------------------------------------------------------
resource "aws_s3_bucket" "artifacts" {
  bucket        = "geo-code-agent-artifacts-${random_id.suffix.hex}"
  force_destroy = true
}

resource "aws_s3_bucket_cors_configuration" "artifacts_cors" {
  bucket = aws_s3_bucket.artifacts.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = ["*"]
    max_age_seconds = 3600
  }
}

# -------------------------------------------------------------------------
# IAM Role for Tier 2 & Tier 3 EC2 Instances (Passwordless S3 Access)
# -------------------------------------------------------------------------
resource "aws_iam_role" "ec2_s3_role" {
  name = "geo-agent-ec2-role-${random_id.suffix.hex}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "s3_access" {
  name = "geo-agent-s3-artifacts-policy"
  role = aws_iam_role.ec2_s3_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:ListBucket"]
      Resource = [
        aws_s3_bucket.artifacts.arn,
        "${aws_s3_bucket.artifacts.arn}/*"
      ]
    }]
  })
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "geo-agent-profile-${random_id.suffix.hex}"
  role = aws_iam_role.ec2_s3_role.name
}

# -------------------------------------------------------------------------
# Security Groups (Tier 3 port 8001 locked strictly to Tier 2 SG)
# -------------------------------------------------------------------------
resource "aws_security_group" "api_sg" {
  name        = "geo-agent-api-sg-${random_id.suffix.hex}"
  description = "Allow HTTP/API traffic to Tier 2 API Node"

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "exec_sg" {
  name        = "geo-agent-exec-sg-${random_id.suffix.hex}"
  description = "Allow port 8001 ONLY from Tier 2 API Node"

  ingress {
    from_port       = 8001
    to_port         = 8001
    protocol        = "tcp"
    security_groups = [aws_security_group.api_sg.id]
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# -------------------------------------------------------------------------
# Tier 3: Execution Node (EC2 Instance #2)
# -------------------------------------------------------------------------
resource "aws_instance" "exec_node" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = var.ssh_key_name != "" ? var.ssh_key_name : null
  vpc_security_group_ids = [aws_security_group.exec_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/user_data_exec.sh", {
    repo_url        = var.repo_url
    repo_branch     = var.repo_branch
    executor_secret = random_password.executor_secret.result
    s3_bucket       = aws_s3_bucket.artifacts.bucket
    aws_region      = var.aws_region
  })

  tags = {
    Name = "geo-code-agent-tier3-exec"
  }
}

# -------------------------------------------------------------------------
# Tier 2: Web API & Control Node (EC2 Instance #1)
# -------------------------------------------------------------------------
resource "aws_instance" "api_node" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = var.ssh_key_name != "" ? var.ssh_key_name : null
  vpc_security_group_ids = [aws_security_group.api_sg.id]
  iam_instance_profile   = aws_iam_instance_profile.ec2_profile.name
  depends_on             = [aws_instance.exec_node]

  root_block_device {
    volume_size = 16
    volume_type = "gp3"
  }

  user_data = templatefile("${path.module}/user_data_api.sh", {
    repo_url        = var.repo_url
    repo_branch     = var.repo_branch
    groq_api_key    = var.groq_api_key
    groq_model      = var.groq_model
    qdrant_url      = var.qdrant_url
    qdrant_api_key  = var.qdrant_api_key
    exec_private_ip = aws_instance.exec_node.private_ip
    executor_secret = random_password.executor_secret.result
    s3_bucket       = aws_s3_bucket.artifacts.bucket
    aws_region      = var.aws_region
    vercel_origin   = var.vercel_origin
  })

  tags = {
    Name = "geo-code-agent-tier2-api"
  }
}