terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
  default_tags {
    tags = {
      Project   = "factored-advisor"
      ManagedBy = "terraform"
    }
  }
}

locals {
  advisor_files = toset([
    "__init__.py", "applications.py", "aws_state.py", "chat_flow.py",
    "data_access.py", "lambda_app.py", "policy.py", "service.py",
    "session.py", "synthetic_data.py", "web.py", "ui/app.css",
    "ui/app.js", "ui/index.html", "ui/review.html", "ui/review.js"
  ])
}

# This allowlist prevents local CSVs, .env files, tests, and SQLite files from
# entering the public function artifact.
data "archive_file" "advisor" {
  type        = "zip"
  output_path = "${path.module}/advisor.zip"

  dynamic "source" {
    for_each = local.advisor_files
    content {
      content  = file("${path.module}/../../advisor/${source.value}")
      filename = "advisor/${source.value}"
    }
  }

  source {
    content  = file("${path.module}/../../plan/conversation_data/source_pack.md")
    filename = "plan/conversation_data/source_pack.md"
  }
}

resource "aws_dynamodb_table" "advisor" {
  name         = "factored-advisor-demo"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  point_in_time_recovery {
    enabled = false
  }
}

resource "aws_cloudwatch_log_group" "advisor" {
  name              = "/aws/lambda/factored-advisor-demo"
  retention_in_days = 7
}

# The app emits fixed fields only: endpoint, status, duration, route, and
# model-attempt events. These queries are saved for the demo operator; they
# run and incur query charges only when opened in CloudWatch Logs Insights.
resource "aws_cloudwatch_query_definition" "requests" {
  name            = "factored-advisor/requests"
  log_group_names = [aws_cloudwatch_log_group.advisor.name]
  query_string    = <<-QUERY
    fields @timestamp, endpoint, status, duration_ms, route
    | filter event = "advisor_request"
    | stats count(*) as requests, pct(duration_ms, 50) as p50_ms,
            pct(duration_ms, 95) as p95_ms by bin(5m), endpoint, status
  QUERY
}

resource "aws_cloudwatch_query_definition" "model_attempts" {
  name            = "factored-advisor/model-attempts"
  log_group_names = [aws_cloudwatch_log_group.advisor.name]
  query_string    = <<-QUERY
    fields @timestamp
    | filter event = "model_attempt"
    | stats count(*) as provider_requests by bin(1h)
  QUERY
}

resource "aws_cloudwatch_log_metric_filter" "app_errors" {
  name           = "factored-advisor-server-errors"
  log_group_name = aws_cloudwatch_log_group.advisor.name
  pattern        = "{ $.event = \"advisor_request\" && $.status >= 500 }"

  metric_transformation {
    name      = "ServerErrors"
    namespace = "FactoredAdvisor"
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "app_errors" {
  alarm_name          = "factored-advisor-server-errors"
  alarm_description   = "The advisor returned an HTTP 5xx response. Console alarm; no notification target is configured."
  namespace           = "FactoredAdvisor"
  metric_name         = "ServerErrors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  alarm_name          = "factored-advisor-lambda-throttles"
  alarm_description   = "Lambda requests were throttled by the regional concurrency quota. Console alarm only."
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = "factored-advisor-demo" }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
}

data "aws_iam_policy_document" "assume_lambda" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "advisor" {
  name               = "factored-advisor-demo-runtime"
  assume_role_policy = data.aws_iam_policy_document.assume_lambda.json
}

data "aws_iam_policy_document" "runtime" {
  statement {
    sid       = "DemoState"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:Scan"]
    resources = [aws_dynamodb_table.advisor.arn]
  }
  statement {
    sid       = "HostedSecret"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${var.secret_parameter_name}"]
  }
  statement {
    sid       = "AppLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.advisor.arn}:*"]
  }
}

data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy" "advisor" {
  name   = "factored-advisor-demo-runtime"
  role   = aws_iam_role.advisor.id
  policy = data.aws_iam_policy_document.runtime.json
}

resource "aws_lambda_function" "advisor" {
  function_name                  = "factored-advisor-demo"
  filename                       = data.archive_file.advisor.output_path
  source_code_hash               = data.archive_file.advisor.output_base64sha256
  role                           = aws_iam_role.advisor.arn
  runtime                        = "python3.12"
  handler                        = "advisor.lambda_app.lambda_handler"
  timeout                        = 60
  memory_size                    = 512
  reserved_concurrent_executions = var.enabled ? -1 : 0
  architectures                  = ["arm64"]

  environment {
    variables = {
      ADVISOR_HOSTED              = "1"
      ADVISOR_TABLE_NAME          = aws_dynamodb_table.advisor.name
      ADVISOR_SECRET_PARAMETER    = var.secret_parameter_name
      ADVISOR_MAX_ANSWERS_PER_DAY = tostring(var.max_answers_per_day)
    }
  }

  depends_on = [aws_iam_role_policy.advisor, aws_cloudwatch_log_group.advisor]
}

resource "aws_lambda_function_url" "advisor" {
  function_name      = aws_lambda_function.advisor.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "public_url" {
  statement_id           = "PublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.advisor.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "public_invoke" {
  statement_id             = "PublicInvokeViaFunctionUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.advisor.function_name
  principal                = "*"
  invoked_via_function_url = true
}
