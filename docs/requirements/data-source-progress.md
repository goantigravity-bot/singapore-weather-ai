# Data Source & Cleansing Progress

本文档记录 Weather AI 项目各数据源的获取进度、清洗状态和质量问题。

> 详细 Bug 清单见 [bugs.md](file:///Users/jinhui/development/tools/claude-skill/docs/bugs.md)、架构决策见 [architecture-decisions.md](file:///Users/jinhui/development/tools/claude-skill/docs/architecture-decisions.md)

---

## 数据源总览

| 数据源 | 类型 | 覆盖范围 | 频率 | 状态 |
|--------|------|----------|------|------|
| [data.gov.sg 传感器](#1-传感器数据) | 温度/湿度/降雨/风/PM2.5 | 2020-01 ~ 至今 | 1 分钟 | ✅ 已完成 |
| [Himawari L1b 卫星](#2-卫星数据多通道) | B08/B11/B13 亮温 | 2020-01 ~ 2026-02 | 10 分钟 | 🔄 下载中 |
| [旧版 JAXA 卫星](#3-旧版单通道卫星已弃用) | 单通道 NC 全盘 | 2025-10 ~ 2026-02 | 10 分钟 | ❌ 已弃用 |

---

## 1. 传感器数据

**来源**: data.gov.sg API (温度/湿度/降雨/PM2.5/风速风向)

### 采集状态
- CSV 文件: `real_sensor_data.csv`
- 覆盖: 2020-01-01 ~ 至今（download_manager.py 实时+回填）
- 约 60+ 基站，1 分钟粒度

### 清洗处理
- 风向分解为 sin/cos 分量（消除 0°/360° 跳变）
- 缺失值填 0
- 按 station_id + timestamp 排序

### 已知问题
- 部分时段 API 返回空数据
- 少量基站坐标缺失（已手动补充 station_coords.json）
- download_manager.py 旧服务已停止（2026-02-17），由新 3ch 脚本替代卫星下载

---

## 2. 卫星数据（多通道）

**来源**: AWS Open Data S3 → Himawari-8/9 AHI L1b HSD

### 波段选择

| 波段 | 波长 | 物理意义 | 用途 |
|------|------|----------|------|
| B08 | 6.2μm | 高层水汽 | 大气湿度 |
| B11 | 8.6μm | 云相态（冰/水） | 区分积雨云 vs 卷云 |
| B13 | 10.4μm | 红外窗区 | 云顶高度/对流强度 |

### 采集状态

```
下载脚本: download_aws_satellite.py (12 workers, ProcessPoolExecutor, t3.xlarge)
解析器: hsd_parser.py (直接二进制解析, 替代 satpy)
数据路径: s3://weather-ai-models-de08370c/processed/satellite-3ch/
文件格式: SAT_{Band}_{YYYYMMDD}_{HHMM}.npy
文件大小: ~6KB/文件, shape (41, 37)
时间基准: UTC
```

| 时段 | 卫星 | Bucket | 状态 |
|------|------|--------|------|
| 2020-01 ~ 2022-12 | Himawari-8 | noaa-himawari8 | 🔄 下载中 |
| 2022-12 ~ 2026-02 | Himawari-9 | noaa-himawari9 | 🔄 下载中 |

- **开始时间**: 2026-02-17 14:51 UTC
- **性能调优**: ADR-010 三项优化（HSD 直接解析 + completed_days 缓存 + 多进程）
- **预计完成**: ~3 天 (实测 ~237 文件/分)
- **监控**: watchdog.sh + SNS 邮件告警 (jinhui.sg@gmail.com)

### 处理流程

```
AWS S3 (L1b HSD, Segment S05 only)
  ↓ s3 cp --no-sign-request
本地 /tmp (BZ2 压缩)
  ↓ hsd_parser.py: bz2.decompress → struct.unpack → np.frombuffer
亮温数组 (550×5500 segment)
  ↓ 固定 crop bounds (455:496, 891:928) — satpy 验证过
裁剪后 (41×37) .npy
  ↓ 上传 S3 → 删本地
s3://weather-ai-models-de08370c/processed/satellite-3ch/
```

### 性能优化历史

| 日期 | 优化 | 效果 |
|------|------|------|
| 02-17 14:51 | 4 workers, t3.large, satpy | ~53 文件/分 |
| 02-17 16:00 | 升级 t3.xlarge, 8 workers | ~69 文件/分 (+30%) |
| 02-17 17:30 | 12 workers | ~107 文件/分 (+55%) |
| 02-17 20:57 | ADR-010: HSD 解析 + 多进程 + 缓存 | 预估 ~150-200 文件/分 |
| 02-17 21:08 | 部署后实测 (新数据处理阶段) | **~237 文件/分 (+120%)** |

#### 部署后实测数据 (02-17 21:08)

| 指标 | 优化前 (satpy+threads) | 优化后 (hsd+process) | 变化 |
|------|----------------------|---------------------|------|
| CPU | 88% us, 7% sy | 96.5% us, 3% sy | 真并行利用更充分 |
| Load Average | 6.41 (4核) | 9.04 | 12 进程真并行 |
| 内存 | 2.5 GB | 2.0 GB | -20% |
| 网络下载 | — | 9,108 KB/s (~9MB/s) | 带宽利用更高 |
| 处理速度 | ~107 文件/分 | **~237 文件/分** | **+120%** |
| 预计总时间 | ~6 天 | **~3 天** | -50% |
| 预计总费用 | ~$30 | **~$15** | -50% |

### 瓶颈分析

#### AWS 限流 — 不是瓶颈

| 服务 | 限制 | 我们的实际用量 | 余量 |
|------|------|-------------|------|
| **S3 GET/HEAD** | 5,500 req/s/prefix | ~1.8 req/s | 3000× |
| **S3 PUT** | 3,500 req/s/prefix | ~0.6 req/s | 5800× |
| **AWS Open Data** | 无显式配额 (fair use) | ~1.8 req/s, ~54KB/s | 远低于阈值 |

> AWS Open Data 无公开速率限制,极端使用时返回 `503 SlowDown`。当前用量远低于触发阈值。

#### CPU — 主要瓶颈（优化前）

12 workers + satpy 时实测:

| 指标 | 值 | 含义 |
|------|-----|------|
| CPU 使用率 | 88% (us+sy) | 接近满载 |
| CPU Idle | 10.7% | 余量极小 |
| Load Average | 6.41 (4 核) | 超核数，任务排队 |
| CPU Steal | 0.9% | T3 积分暂未被限 |

原因: satpy Scene 初始化 + dask + xarray 开销大; Python GIL 限制多线程 CPU 密集并行。

#### 优化方案评估

| 方案 | 投入 | 预期收益 | 采纳 |
|------|------|---------|------|
| HSD 直接解析替代 satpy | 新文件 ~120 行 | CPU -45%, 速度 +80% | ✅ ADR-010 |
| Thread → Process | 改 ~20 行 | 多核真并行 | ✅ ADR-010 |
| completed_days 缓存 | 改 ~15 行 | 重启追赶 → 0 秒 | ✅ ADR-010 |
| 换 c6i.xlarge | 换实例 | 单核 +30%, 价格更低 | ❌ 暂不需要 |
| 升级 t3.2xlarge (8 vCPU) | 双倍费用 | 受网络带宽限制 | ❌ 性价比低 |

### 已解决的问题
- satpy `resample()` 全盘 KDTree 超时 → 改用 `get_lonlats()` 直接切片
- boto3 并发创建 client 线程安全 → ~~主线程预创建 client 池~~ → 多进程 + 进程级缓存
- 8 workers OOM (t3.large 8GB) → 升级 t3.xlarge (16GB)，最终 12 workers
- ~~OpenMP 冲突 (torch + satpy)~~ → 不再使用 satpy，问题消失
- CPU 饱和 (88%, GIL 限制) → HSD 直接解析 (-45% CPU) + ProcessPoolExecutor (真并行)
- 重启 S3 扫描延迟 → .completed_days 本地缓存（零请求跳过）

### 时区注意
- 卫星文件名 = **UTC**
- 传感器 CSV = **SGT (UTC+8)**
- `prepare_station_data.py` 查找时减 8 小时

---

## 3. 旧版单通道卫星（已弃用）

**来源**: JAXA FTP → Himawari NC 全盘文件

- 路径: `processed_data/SAT_128_YYYYMMDD_HHMM.npy` (128×128, 单通道)
- 覆盖: 2025-10 ~ 2026-02
- **已弃用原因**: 被 3 通道 L1b 方案取代
- S3 旧 NC 文件 (10.1TB) 已于 2026-02-17 删除
- 本地 processed_data/ 保留用于兼容旧模型

---

## 4. 存储使用

### S3 (s3://weather-ai-models-de08370c)

| 前缀 | 文件数 | 大小 | 内容 |
|------|--------|------|------|
| processed/satellite-3ch/ | ~970K (最终) | ~6GB | 新 3ch .npy |
| processed/satellite/ | ~50K | ~2.5GB | 旧单通道 .npy |
| models/ | ~280 | 75MB | 训练模型权重 |
| satellite/ | 0 | 0 | ~~10.1TB 旧 NC~~ 已删 |

### 预估月费
- 清理前: ~$53/月 (10.1TB)
- 清理后: **< $1/月** (~8.5GB)
