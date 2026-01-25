# 自动化训练流程使用指南

## 概述

这是一个完全自动化的模型训练系统，可以：
1. 📡 从JAXA FTP下载卫星数据
2. 🌡️ 从NEA API获取传感器数据（增量更新）
3. 🖼️ 预处理卫星图像
4. 🧠 训练天气预测模型
5. 📊 评估模型性能
6. 📧 自动发送训练报告邮件

## 快速开始

### 1. 环境配置

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export SENDER_EMAIL="your-email@gmail.com"
export SENDER_PASSWORD="your-gmail-app-password"
export RECIPIENT_EMAIL="recipient@example.com"  # 可选，默认同发件人

# JAXA FTP凭据（已在download_jaxa_data.py中配置）
export JAXA_USER="your-jaxa-username"
export JAXA_PASS="your-jaxa-password"
```

#### 获取Gmail App Password

1. 访问 https://myaccount.google.com/apppasswords
2. 选择"邮件"和"其他设备"
3. 生成密码并复制
4. 使用该密码作为 `SENDER_PASSWORD`

### 2. 测试邮件系统

```bash
# 测试邮件发送
python3 notification.py
```

如果配置正确，你将收到一封测试邮件。

### 3. 测试报告生成

```bash
# 生成测试报告
python3 generate_report.py
```

报告将保存在 `training_reports/test_report.html`，可以在浏览器中打开查看。

### 4. 运行完整训练流程

```bash
# 手动运行一次
python3 auto_train_pipeline.py
```

流程将依次执行：
1. 下载最近24小时的卫星数据
2. 下载增量传感器数据
3. 预处理卫星图像
4. 训练模型
5. 评估模型
6. 生成并发送报告

### 5. 设置定时任务（每日自动训练）

#### macOS/Linux (使用 cron)

```bash
# 编辑crontab
crontab -e

# 添加以下行（每天凌晨2点执行）
0 2 * * * cd /Users/jinhui/development/tools/claude-skill && /usr/bin/python3 auto_train_pipeline.py >> training_logs/cron.log 2>&1
```

#### 或者使用 launchd (macOS推荐)

创建 `~/Library/LaunchAgents/com.weatherai.training.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.weatherai.training</string>
    
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/jinhui/development/tools/claude-skill/auto_train_pipeline.py</string>
    </array>
    
    <key>WorkingDirectory</key>
    <string>/Users/jinhui/development/tools/claude-skill</string>
    
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    
    <key>StandardOutPath</key>
    <string>/Users/jinhui/development/tools/claude-skill/training_logs/launchd.log</string>
    
    <key>StandardErrorPath</key>
    <string>/Users/jinhui/development/tools/claude-skill/training_logs/launchd_error.log</string>
    
    <key>EnvironmentVariables</key>
    <dict>
        <key>SENDER_EMAIL</key>
        <string>your-email@gmail.com</string>
        <key>SENDER_PASSWORD</key>
        <string>your-app-password</string>
    </dict>
</dict>
</plist>
```

加载任务：
```bash
launchctl load ~/Library/LaunchAgents/com.weatherai.training.plist
```

## 文件结构

```
.
├── auto_train_pipeline.py      # 主编排脚本
├── notification.py             # 邮件通知系统
├── generate_report.py          # 报告生成器
├── download_jaxa_data.py       # 卫星数据下载
├── fetch_and_process_gov_data.py  # 传感器数据下载
├── preprocess_images.py        # 图像预处理
├── train.py                    # 模型训练
├── evaluate.py                 # 模型评估
├── training_state.json         # 训练状态（自动生成）
├── evaluation_results.json     # 评估结果（自动生成）
├── training_logs/              # 训练日志目录
│   ├── training_YYYYMMDD_HHMMSS.log
│   └── cron.log
└── training_reports/           # 训练报告目录
    ├── report_YYYYMMDD_HHMMSS.html
    └── latest_metrics.json
```

## 功能特性

### 增量数据更新

系统会自动记录上次训练的日期，下次只下载新数据：

```json
// training_state.json
{
  "last_training_end_date": "2026-01-25"
}
```

### 失败重试

每个步骤失败后会自动重试2次（可配置）：

```python
MAX_RETRIES = 2  # 在 auto_train_pipeline.py 中修改
```

### 邮件通知

- ✅ **成功通知**: 包含完整HTML报告和评估图表
- ❌ **失败通知**: 包含错误信息和日志文件

### 性能对比

报告会自动对比本次和上次训练的性能：

| 指标 | 本次训练 | 上次训练 | 变化 |
|------|----------|----------|------|
| MAE  | 0.1234   | 0.1456   | ↓15% |
| RMSE | 0.2345   | 0.2567   | ↓8%  |

## 故障排查

### 邮件发送失败

1. 检查环境变量是否设置正确
2. 确认使用的是Gmail App Password，不是账户密码
3. 检查Gmail账户是否开启了"允许不够安全的应用"

### 数据下载失败

1. 检查网络连接
2. 验证JAXA FTP凭据
3. 查看日志文件了解详细错误

### 训练失败

1. 检查数据文件是否完整
2. 确认有足够的磁盘空间
3. 查看 `training_logs/` 中的详细日志

## 高级配置

### 修改训练参数

编辑 `train.py`:

```python
BATCH_SIZE = 4
LEARNING_RATE = 1e-3
EPOCHS = 30
```

### 修改数据下载范围

编辑 `auto_train_pipeline.py` 中的 `step_1_download_satellite_data`:

```python
# 下载最近48小时的数据
cmd = [
    "python3", "download_jaxa_data.py",
    "--mode", "batch",
    "--hours", "48"  # 修改这里
]
```

### 自定义报告样式

编辑 `generate_report.py` 中的HTML模板和CSS样式。

## 监控和维护

### 查看日志

```bash
# 查看最新日志
tail -f training_logs/training_*.log

# 查看cron日志
tail -f training_logs/cron.log
```

### 清理旧文件

```bash
# 删除30天前的日志
find training_logs/ -name "*.log" -mtime +30 -delete

# 删除旧报告（保留最近10个）
ls -t training_reports/report_*.html | tail -n +11 | xargs rm
```

### 数据库备份

定期备份训练状态和指标：

```bash
# 备份状态文件
cp training_state.json training_state.json.bak
cp training_reports/latest_metrics.json training_reports/latest_metrics.json.bak
```

## 支持

如有问题，请查看：
1. 日志文件 `training_logs/`
2. 评估结果 `evaluation_results.json`
3. 训练状态 `training_state.json`

或联系开发者。
