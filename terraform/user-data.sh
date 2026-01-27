#!/bin/bash
# EC2实例初始化脚本（User Data）
# 在实例首次启动时自动执行

set -e

# 日志输出
exec > >(tee /var/log/user-data.log)
exec 2>&1

echo "========================================="
echo "开始初始化 ${project_name} 服务器"
echo "时间: $(date)"
echo "========================================="

# 更新系统
echo "更新系统包..."
apt-get update
apt-get upgrade -y

# 安装基础工具
echo "安装基础工具..."
apt-get install -y \
    python3-pip \
    python3-venv \
    git \
    htop \
    tmux \
    curl \
    wget \
    unzip \
    build-essential

# 创建项目目录
echo "创建项目目录..."
mkdir -p /home/ubuntu/${project_name}
chown ubuntu:ubuntu /home/ubuntu/${project_name}

# 配置Python虚拟环境
echo "配置Python虚拟环境..."
su - ubuntu -c "cd /home/ubuntu/${project_name} && python3 -m venv venv"

# 配置自动更新（可选）
echo "配置自动安全更新..."
apt-get install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades

# 配置防火墙
echo "配置UFW防火墙..."
ufw --force enable
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8000/tcp

# 创建欢迎消息
cat > /etc/motd << 'EOF'
========================================
  新加坡天气AI系统
  Weather AI System
========================================
  
  项目目录: /home/ubuntu/${project_name}
  虚拟环境: source venv/bin/activate
  
  常用命令:
    - 查看API状态: systemctl status weather-api
    - 查看API日志: journalctl -u weather-api -f
    - 运行训练: python3 auto_train_pipeline.py
  
========================================
EOF

echo "========================================="
echo "初始化完成！"
echo "时间: $(date)"
echo "========================================="
