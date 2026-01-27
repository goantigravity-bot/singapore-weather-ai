#!/bin/bash
# 配置 CloudFront 代理 API，解决 Mixed Content 问题
# 此脚本将添加 EC2 作为 CloudFront 的第二个 Origin，并设置 /api/* 路由

set -e

DISTRIBUTION_ID="E3NTCXM5BZ2EUY"
EC2_INSTANCE_ID="i-004dffd96ed716316"
REGION="ap-southeast-1"

# 获取 EC2 公有 DNS（CloudFront 不支持 IP 地址）
EC2_DNS=$(aws ec2 describe-instances --instance-ids $EC2_INSTANCE_ID --region $REGION --query "Reservations[0].Instances[0].PublicDnsName" --output text)

if [ -z "$EC2_DNS" ] || [ "$EC2_DNS" == "None" ]; then
    echo "❌ 无法获取 EC2 公有 DNS。请确保实例正在运行。"
    exit 1
fi

echo "🔧 配置 CloudFront 代理 API..."
echo "Distribution ID: $DISTRIBUTION_ID"
echo "EC2 DNS: $EC2_DNS"

# 获取当前配置
echo "📥 获取当前 CloudFront 配置..."
aws cloudfront get-distribution-config --id $DISTRIBUTION_ID > /tmp/cf-original.json
ETAG=$(cat /tmp/cf-original.json | python3 -c "import json,sys; print(json.load(sys.stdin)['ETag'])")
echo "ETag: $ETAG"

# 使用 Python 修改配置
export EC2_DNS
python3 << 'PYTHON_SCRIPT'
import json
import os

ec2_dns = os.environ.get('EC2_DNS', '')

with open('/tmp/cf-original.json', 'r') as f:
    data = json.load(f)

config = data['DistributionConfig']

# 添加 EC2 作为新的 Origin
ec2_origin = {
    "Id": "EC2-weather-api",
    "DomainName": ec2_dns,
    "OriginPath": "",
    "CustomHeaders": {"Quantity": 0},
    "CustomOriginConfig": {
        "HTTPPort": 8000,
        "HTTPSPort": 443,
        "OriginProtocolPolicy": "http-only",
        "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
        "OriginReadTimeout": 30,
        "OriginKeepaliveTimeout": 5
    },
    "ConnectionAttempts": 3,
    "ConnectionTimeout": 10,
    "OriginShield": {"Enabled": False},
    "OriginAccessControlId": ""
}

# 检查是否已存在 EC2 Origin
existing_origins = config['Origins']['Items']
ec2_exists = any(o['Id'] == 'EC2-weather-api' for o in existing_origins)

if not ec2_exists:
    existing_origins.append(ec2_origin)
    config['Origins']['Quantity'] = len(existing_origins)
    print("✅ 添加 EC2 Origin")
else:
    print("ℹ️  EC2 Origin 已存在，更新配置")
    for i, o in enumerate(existing_origins):
        if o['Id'] == 'EC2-weather-api':
            existing_origins[i] = ec2_origin

# 添加 /api/* 的 Cache Behavior
api_behavior = {
    "PathPattern": "/api/*",
    "TargetOriginId": "EC2-weather-api",
    "TrustedSigners": {"Enabled": False, "Quantity": 0},
    "TrustedKeyGroups": {"Enabled": False, "Quantity": 0},
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
        "Quantity": 7,
        "Items": ["HEAD", "DELETE", "POST", "GET", "OPTIONS", "PUT", "PATCH"],
        "CachedMethods": {"Quantity": 2, "Items": ["HEAD", "GET"]}
    },
    "SmoothStreaming": False,
    "Compress": True,
    "LambdaFunctionAssociations": {"Quantity": 0},
    "FunctionAssociations": {"Quantity": 0},
    "FieldLevelEncryptionId": "",
    "GrpcConfig": {"Enabled": False},
    "ForwardedValues": {
        "QueryString": True,  # 转发查询字符串
        "Cookies": {"Forward": "all"},
        "Headers": {
            "Quantity": 4,
            "Items": ["Origin", "Access-Control-Request-Headers", "Access-Control-Request-Method", "Authorization"]
        },
        "QueryStringCacheKeys": {"Quantity": 0}
    },
    "MinTTL": 0,
    "DefaultTTL": 0,  # 不缓存 API 响应
    "MaxTTL": 0
}

# 检查是否已存在 /api/* behavior
existing_behaviors = config.get('CacheBehaviors', {}).get('Items', [])
api_exists = any(b.get('PathPattern') == '/api/*' for b in existing_behaviors)

if not api_exists:
    existing_behaviors.append(api_behavior)
    config['CacheBehaviors'] = {
        "Quantity": len(existing_behaviors),
        "Items": existing_behaviors
    }
    print("✅ 添加 /api/* Cache Behavior")
else:
    print("ℹ️  /api/* Cache Behavior 已存在，更新配置")
    for i, b in enumerate(existing_behaviors):
        if b.get('PathPattern') == '/api/*':
            existing_behaviors[i] = api_behavior
    config['CacheBehaviors']['Items'] = existing_behaviors

# 保存新配置
with open('/tmp/cf-updated.json', 'w') as f:
    json.dump(config, f, indent=2)

print("✅ 配置已保存到 /tmp/cf-updated.json")
PYTHON_SCRIPT

# 更新 CloudFront 配置
echo "📤 更新 CloudFront 配置..."
aws cloudfront update-distribution \
    --id $DISTRIBUTION_ID \
    --if-match $ETAG \
    --distribution-config file:///tmp/cf-updated.json

echo ""
echo "✅ CloudFront 配置更新成功！"
echo ""
echo "⏳ 等待分发部署完成（通常需要 5-15 分钟）..."
echo "   可以使用以下命令检查状态："
echo "   aws cloudfront get-distribution --id $DISTRIBUTION_ID --query 'Distribution.Status'"
echo ""
echo "📝 接下来需要更新前端代码："
echo "   将 API 调用从 http://EC2_IP:8000/xxx 改为 /api/xxx"
echo ""
