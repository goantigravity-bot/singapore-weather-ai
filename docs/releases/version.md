# Version History

## v0.11.0 (2026-02-17)

**Telegram 通知集成 + GCC 账号 Terraform + 多通道下载优化**

- 🔔 Telegram Bot 集成 (@WeatherAIAlertBot): rain alert, system alert, test message
- 🏗️ GCC AWS 账号 Terraform 配置 (`infra/terraform-gcc/`)
- ⚡ HSD 解析器替代 satpy (10x 性能提升)
- 📡 `download_aws_satellite.py` 多通道 3ch 下载
- 🌡️ 传感器数据下载和预处理
- 🧠 单站点模型训练框架
- 📝 TODO 清单、架构决策文档、英文模型调优报告

## v0.10.0 (2026-02-17)

**文档整理 + NOAA 数据源迁移 + 模型优化实验**

## v0.9.1 (2026-02-15)

**风场动画 + 卫星云图叠加**

- 🌬️ Canvas 粒子动画风场可视化 (IDW 插值)
- ☁️ 卫星云图叠加动画

## v0.9.0 (2026-02-14)

**基础设施修复 + 数据管道报告 + 下载并行化**

- 实时传感器数据抓取 + 时间参数化预测 API
- WeightedRandomSampler 平衡雨/晴训练批次
- 性能测试 v2 + 精度 API 优化

## v0.8.0 (2026-02-12)

**预测 vs 实际闭环**

- 数据存储 schema: forecast_result + actual_result
- ER 图文档更新
- 文件锁 + 单 worker 收集器

## v0.7.0 (2026-02-10)

**SQLite 缓存层 + ThreadPool 并行推理**

## v0.6.1 (2026-02-09)

**服务独立环境配置**

## v0.6.0 (2026-02-08)

**修复训练管道 + API 日志增强**

- 训练流水线 7 个 bug 修复
- Vitest 测试框架
- 邮件通知多收件人 (CC_EMAILS)

## v0.5.0 (2026-02-05)

**AWS 部署 + 本地开发改进**

- CloudFront API 代理
- PM2.5 数据集成
- 自动化训练管线
- 监控仪表盘 + 并行下载优化

## v0.4.0 (2026-02-03)

**传感器半径限制 + 日志重构**

- 强制 10km 半径限制
- print → logging 重构

## v0.3.0 (2026-02-02)

**Landmark Path 功能**

- 智能路径搜索

## v0.2.0 (2026-02-01)

**热门搜索 + 统计页面 + 移动端**

## v0.1.0 (2026-01-26)

**初始版本**

- 全栈实现: React + FastAPI
- 预测 API + 批量预测
- 新加坡天气 AI 系统初始提交
