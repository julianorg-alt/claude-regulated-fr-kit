variable "name" {
  description = "Prefix of the security groups and endpoints."
  type        = string
  default     = "claude-gateway"
}

variable "region" {
  description = "Region of the VPC and of the Bedrock endpoints (EU member state)."
  type        = string
  default     = "eu-west-3"
}

variable "vpc_id" {
  description = "VPC that hosts the gateway."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnets for the interface endpoints, one per Availability Zone."
  type        = list(string)
  validation {
    condition     = length(var.subnet_ids) > 0
    error_message = "At least one subnet is required."
  }
}

variable "gateway_role_arn" {
  description = "IAM role of the gateway (output role_arn of bedrock-eu-access): the only principal the endpoint policy lets through."
  type        = string
}

variable "enable_mantle" {
  description = "Also create the bedrock-mantle endpoint (In-Region inference, mode in_region_mantle)."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags for every resource."
  type        = map(string)
  default     = {}
}
