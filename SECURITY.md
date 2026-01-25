# 安全配置说明

## ⚠️ 重要提示

本项目包含敏感信息（邮箱密码、API凭据等），请务必遵循以下安全实践：

## 🔐 敏感文件

以下文件包含敏感信息，**不应提交到Git**：

- `env.sh` - 环境变量配置（包含密码）
- `*.pem`, `*.key` - 证书和密钥文件
- `weather.db` - 数据库（可能包含用户数据）

这些文件已添加到 `.gitignore`。

## 📝 配置步骤

### 1. 创建环境变量文件

```bash
# 复制模板文件
cp env.sh.template env.sh

# 编辑文件，填入实际值
vi env.sh
```

### 2. 配置邮件通知

在 `env.sh` 中设置：

```bash
export SENDER_EMAIL="your-email@gmail.com"
export SENDER_PASSWORD="your-gmail-app-password"
export RECIPIENT_EMAIL="recipient@example.com"
```

**获取Gmail App Password**:
1. 访问 https://myaccount.google.com/apppasswords
2. 选择"邮件"和"其他设备"
3. 生成密码并复制
4. 使用该密码作为 `SENDER_PASSWORD`

### 3. 配置JAXA FTP凭据

在 `env.sh` 中设置：

```bash
export JAXA_USER="your-jaxa-username"
export JAXA_PASS="your-jaxa-password"
```

**注册JAXA账户**:
- 访问 https://www.eorc.jaxa.jp/ptree/registration_top.html
- 注册并获取FTP凭据

### 4. 加载环境变量

```bash
# 每次使用前加载
source env.sh

# 或者添加到 ~/.zshrc 或 ~/.bashrc
echo "source /path/to/project/env.sh" >> ~/.zshrc
```

### 5. 验证配置

```bash
python3 test_auto_training.py
```

## 🚨 如果不小心提交了敏感信息

### 立即从Git历史中移除

```bash
# 从Git缓存中移除
git rm --cached env.sh

# 添加到.gitignore
echo "env.sh" >> .gitignore

# 提交更改
git add .gitignore
git commit -m "chore: remove sensitive file from git"

# 从历史中彻底删除（谨慎使用）
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch env.sh" \
  --prune-empty --tag-name-filter cat -- --all

# 强制推送（会重写历史）
git push origin --force --all
```

### 更改已泄露的密码

1. **Gmail App Password**: 删除旧密码，生成新密码
2. **JAXA凭据**: 联系JAXA重置密码

## ✅ 最佳实践

1. **永远不要**硬编码密码
2. **使用环境变量**存储敏感信息
3. **定期轮换**密码和API密钥
4. **检查Git历史**确保没有敏感信息
5. **使用 `.gitignore`** 防止意外提交

## 📚 相关文档

- [AUTO_TRAINING_README.md](AUTO_TRAINING_README.md) - 自动化训练系统使用指南
- [env.sh.template](env.sh.template) - 环境变量配置模板
