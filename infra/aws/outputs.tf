output "judge_url" {
  value       = aws_lambda_function_url.advisor.function_url
  description = "Public HTTPS judge URL; unavailable while enabled=false."
}

output "enabled" {
  value = var.enabled
}

output "state_table" {
  value = aws_dynamodb_table.advisor.name
}
