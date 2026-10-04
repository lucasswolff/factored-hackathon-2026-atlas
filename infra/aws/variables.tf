variable "aws_profile" {
  type        = string
  description = "Dedicated deployment profile; never use an existing unrelated identity."
  default     = "factored-hackathon-2026"
}

variable "aws_region" {
  type    = string
  default = "us-east-2"
}

variable "secret_parameter_name" {
  type    = string
  default = "/factored/advisor/hosted"
  validation {
    condition     = startswith(var.secret_parameter_name, "/")
    error_message = "Use a hierarchical SSM parameter name starting with /."
  }
}

variable "enabled" {
  type        = bool
  description = "False sets Lambda reserved concurrency to zero while retaining the URL and state."
  default     = false
}

variable "max_answers_per_day" {
  type    = number
  description = "Answer budget; the application allows up to two provider attempts per configured answer."
  default = 200
  validation {
    condition     = var.max_answers_per_day >= 1 && var.max_answers_per_day <= 200
    error_message = "The daily answer cap must be between 1 and 200."
  }
}
