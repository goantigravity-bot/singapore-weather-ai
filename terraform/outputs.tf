# Terraform输出值

output "ec2_public_ip" {
  description = "EC2实例公网IP地址"
  value       = var.use_elastic_ip ? aws_eip.weather_api[0].public_ip : aws_instance.weather_api.public_ip
}

output "ec2_instance_id" {
  description = "EC2实例ID"
  value       = aws_instance.weather_api.id
}

output "ssh_command" {
  description = "SSH连接命令"
  value       = "ssh -i ~/.ssh/${var.project_name}-key.pem ubuntu@${var.use_elastic_ip ? aws_eip.weather_api[0].public_ip : aws_instance.weather_api.public_ip}"
}

output "api_url" {
  description = "API访问URL"
  value       = var.domain_name != "" ? "https://api.${var.domain_name}" : "http://${var.use_elastic_ip ? aws_eip.weather_api[0].public_ip : aws_instance.weather_api.public_ip}:8000"
}

output "s3_bucket_name" {
  description = "前端S3存储桶名称"
  value       = aws_s3_bucket.frontend.id
}

output "s3_website_endpoint" {
  description = "S3网站端点"
  value       = aws_s3_bucket_website_configuration.frontend.website_endpoint
}

output "cloudfront_domain" {
  description = "CloudFront域名"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.frontend[0].domain_name : "Not enabled"
}

output "cloudfront_distribution_id" {
  description = "CloudFront分发ID"
  value       = var.enable_cloudfront ? aws_cloudfront_distribution.frontend[0].id : "Not enabled"
}

output "frontend_url" {
  description = "前端访问URL"
  value       = var.domain_name != "" ? "https://${var.domain_name}" : (var.enable_cloudfront ? "https://${aws_cloudfront_distribution.frontend[0].domain_name}" : "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}")
}

output "deployment_summary" {
  description = "部署摘要"
  value = <<-EOT
  
  ========================================
  部署完成！
  ========================================
  
  后端API:
    URL: ${var.domain_name != "" ? "https://api.${var.domain_name}" : "http://${var.use_elastic_ip ? aws_eip.weather_api[0].public_ip : aws_instance.weather_api.public_ip}:8000"}
    SSH: ssh -i ~/.ssh/${var.project_name}-key.pem ubuntu@${var.use_elastic_ip ? aws_eip.weather_api[0].public_ip : aws_instance.weather_api.public_ip}
  
  前端:
    URL: ${var.domain_name != "" ? "https://${var.domain_name}" : (var.enable_cloudfront ? "https://${aws_cloudfront_distribution.frontend[0].domain_name}" : "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}")}
    S3 Bucket: ${aws_s3_bucket.frontend.id}
    ${var.enable_cloudfront ? "CloudFront ID: ${aws_cloudfront_distribution.frontend[0].id}" : ""}
  
  下一步:
    1. 上传代码到EC2: ./deploy-all.sh
    2. 配置环境变量
    3. 启动服务
  
  ========================================
  EOT
}
