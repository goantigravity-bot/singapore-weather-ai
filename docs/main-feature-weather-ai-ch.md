# 🌦️ 新加坡天气AI预测系统 - 功能清单

> **版本**: 0.5 | **更新日期**: 2026-02-07

---

## 1. 数据采集与处理

### 1.1 卫星数据采集 (`download_jaxa_data.py`)
- 从 JAXA FTP 服务器自动下载 Himawari-9 红外卫星云图
- 支持批量下载和增量更新
- 自动裁剪新加坡区域（103.6°E-104.1°E, 1.15°N-1.50°N）
- 并行下载优化（xargs -P），大幅提升吞吐量

### 1.2 传感器数据采集 (`fetch_and_process_gov_data.py`)
- 从 NEA（国家环境局）API 获取实时气象数据
- 数据类型：温度、湿度、降雨量、PM2.5
- SSL 证书验证和错误处理
- 自动重采样到 10 分钟间隔

### 1.3 图像预处理 (`preprocess_images.py`)
- NetCDF 格式转换为 NumPy 数组
- 支持多输入文件夹批处理
- 数据归一化和标准化

### 1.4 智能数据对齐 (`convert_govdata_to_csv.py`)
- 卫星与传感器时间戳 100% 匹配
- 自动处理时区转换（UTC ↔ SGT）

---

## 2. 深度学习模型

### 2.1 双分支融合模型 (`weather_fusion_model.py`)

```
卫星图像 → CNN (SatelliteEncoder) ──┐
                                    ├─→ 融合层 → 降雨预测
传感器序列 → LSTM (SensorEncoder) ──┘
```

- **SatelliteEncoder**: 3 层 Conv2d + BatchNorm + ReLU + AdaptiveAvgPool
- **SensorEncoder**: LSTM 时序编码器
- **FusionHead**: 全连接 + Dropout
- **输出**: 未来 10 分钟降雨量预测

### 2.2 训练功能 (`train.py`)
- GPU/CPU/MPS 自适应训练
- 增量学习：自动加载已有模型继续训练
- 特征维度自适应（3→4 features 智能迁移）
- 动态 Epochs 配置（首次 30 / 增量 5）
- 环境变量覆盖支持

### 2.3 模型评估 (`evaluate.py`)
- MAE（平均绝对误差）
- RMSE（均方根误差）
- 分类准确率（雨/无雨）
- 可视化评估图表生成

---

## 3. 自动化训练系统

### 3.1 端到端训练流水线 (`auto_train_pipeline.py`)
完整自动化流程：
1. 下载最新卫星数据
2. 获取增量传感器数据
3. 预处理图像
4. 训练模型
5. 评估性能
6. 生成 HTML 报告
7. 发送邮件通知

### 3.2 历史批量调度器 (`training_scheduler.py`)
- Day-by-Day 批量训练（2025-10 至 2026-01）
- S3 数据就绪检测（`.complete` 标记）
- 训练-清理-归档工作流
- 实时状态同步到 S3 监控仪表盘
- 失败自动重试机制

### 3.3 滑窗训练 (`train_rolling_window.py`)
- 按天/10天窗口分批训练
- S3 检查点保存和恢复
- 训练历史合并上传

### 3.4 训练历史管理 (`training_history.py`)
- 训练指标记录（时间戳、耗时、MAE、RMSE）
- 统计分析：平均训练时长、性能趋势

### 3.5 邮件通知 (`notification.py`)
- 训练成功/失败自动通知
- HTML 邮件模板 + 附件（报告、图表、日志）
- Gmail SMTP 集成

### 3.6 HTML 报告生成 (`generate_report.py`)
- 训练概览和时间线
- 性能指标对比（本次 vs 上次）
- 响应式设计，支持移动端查看

---

## 4. 预测 API 服务 (`api.py`)

### 4.1 核心预测接口

| 端点 | 方法 | 功能 |
|------|------|------|
| `/predict` | GET | 单点天气预测（地名/经纬度） |
| `/predict/path` | GET | 路径天气预测（沿路线采样） |
| `/health` | GET | 健康检查 |
| `/stations` | GET | 气象站信息 |
| `/log-search` | POST | 记录搜索历史 |
| `/popular-searches` | GET | 热门搜索统计 |

### 4.2 核心算法 (`predict.py`)
- **IDW 空间插值**: 反距离加权，3 个最近传感器协同预测
- **Haversine 距离**: 地理空间精确计算
- **OpenStreetMap 集成**: 正/反向地理编码
- **路径采样**: 沿路线每 2km 一个预测点

### 4.3 技术特性
- CORS 跨域支持
- 双路由注册（根路径 + `/api` 前缀）
- SPA 静态文件托管
- SQLite 搜索历史存储
- 模型热加载

---

## 5. 前端应用（React + TypeScript + Vite）

### 5.1 页面结构

| 页面 | 组件 | 功能 |
|------|------|------|
| 首页 | `MapComponent` | Leaflet 交互式地图，点击获取预测 |
| 首页 | `ForecastPanel` | 天气预测结果展示 |
| 首页 | `QuickLinks` | 快捷搜索入口 |
| 统计 | `StatsPage` | 搜索数据统计 |
| 监控 | `TrainingMonitor` | 三标签页训练监控仪表盘 |
| 设置 | `SettingsPage` | 用户配置（站点可见性等） |
| 关于 | `AboutPage` | 项目介绍 |

### 5.2 前端特性
- 交互式地图：点击任意位置获取天气预测
- 路径搜索：输入地标名称获取沿途天气
- 站点标记：可配置的气象站显示/隐藏
- 全局配置上下文（`ConfigContext`），localStorage 持久化
- 响应式设计：桌面/移动端适配
- 侧边导航菜单（`SideMenu`）

---

## 6. 监控仪表盘 (`TrainingMonitor.tsx` + `monitor_api.py`)

### 6.1 Chrome 风格三标签页

| 标签 | 内容 |
|------|------|
| 📥 文件下载 | 每日下载进度、完成天数、卫星/NEA 文件计数 |
| 🧠 训练流程 | 四阶段步进器、批次进度、训练历史表格 |
| 🚀 API 应用 | 模型/传感器同步状态、最后同步时间 |

### 6.2 日志查看功能
- 📋 日志 Modal 弹窗（S3/本地日志）
- 语法高亮：ERROR（红）、WARNING（橙）、SUCCESS（绿）
- 每 5 秒自动刷新

### 6.3 监控 API 端点

| 端点 | 功能 |
|------|------|
| `GET /monitor/overview` | 端到端状态总览 |
| `GET /monitor/download` | 下载状态 |
| `GET /monitor/training` | 训练状态 + 历史 |
| `GET /monitor/sync` | API 同步状态 |
| `GET /monitor/logs/{type}` | 日志内容 |

---

## 7. 基础设施（AWS 3 服务器架构）

| 服务器 | 实例类型 | IP | 用途 |
|--------|----------|-----|------|
| API 服务器 | t3.medium | 3.0.28.161 | FastAPI + 前端 SPA 托管 |
| 训练服务器 | t3.large | 46.137.236.8 | 模型训练 + S3 同步 |
| 下载服务器 | t3.micro | 18.142.90.30 | 并行 FTP 数据采集 |

### S3 数据湖
- **存储桶**: `weather-ai-models-de08370c`
- 模型存储（`models/`）
- 卫星数据暂存（`satellite/`）
- 政府数据（`govdata/`）
- 训练状态（`state/`）
- 历史归档（`archived/`）

---

## 8. DevOps 与部署

| 功能 | 文件 |
|------|------|
| Docker 容器化 | `Dockerfile`, `Dockerfile.api` |
| 一键部署 | `deploy-all.sh` |
| 本地开发 | `run-local.sh`, `stop-local.sh` |
| CloudFront HTTPS 代理 | `setup-cloudfront-api-proxy.sh` |
| 基础设施验证 | `verify-infrastructure.sh` |
| 模型同步到 S3 | `sync_model_to_s3.sh` |
| 从 S3 拉取模型 | `fetch_latest_model.sh` |
| Cron 自动任务 | 10 分钟模型/数据同步 |

---

## 9. 测试覆盖

### 前端测试（Vitest）

| 文件 | 覆盖范围 |
|------|----------|
| `StatsPage.test.tsx` | 统计页面 |
| `TrainingMonitor.test.tsx` | 监控仪表盘 |
| `AboutPage.test.tsx` | 关于页面 |
| `ConfigContext.test.tsx` | 配置上下文 |
| `SettingsPage.test.tsx` | 设置页面 |

### 后端测试（Python）

| 文件 | 覆盖范围 |
|------|----------|
| `test_api.py` | API 接口测试 |
| `test_auto_training.py` | 自动训练测试 |
| `verify_deployment.py` | 部署验证 |
| `verify_pm25_api.py` | PM2.5 API 验证 |

---

## 10. 系统性能指标

| 指标 | 数值 |
|------|------|
| 模型 MAE | ~0.12 mm |
| 模型 RMSE | ~0.23 mm |
| 分类准确率 | ~85% |
| 单点预测响应 | <200ms |
| 路径预测响应 | <1s（10 采样点） |
| 并发支持 | 100+ req/s |
| 模型文件大小 | ~270KB |

---

**项目仓库**: https://github.com/goantigravity-bot/singapore-weather-ai
