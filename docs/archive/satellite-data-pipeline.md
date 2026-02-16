# 卫星云图数据管道 — Walkthrough

## 数据源：NOAA Himawari-9 AWS Open Data

| 项目 | 值 |
|------|-----|
| S3 Bucket | `s3://noaa-himawari9/` (免费, `--no-sign-request`) |
| 产品 | `AHI-L2-FLDK-ISatSS` (Full Disk, ISatSS 处理) |
| 波段 | Band 13 (C13) — 10.4μm 红外，亮温 (TBB) |
| Tile | T036 — 覆盖新加坡及周边区域 |
| 时间分辨率 | 每 10 分钟一帧 |
| 空间分辨率 | 2km/pixel (原始), 裁剪后 128×128 |

### NOAA S3 目录结构

```
s3://noaa-himawari9/AHI-L2-FLDK-ISatSS/
└── YYYY/MM/DD/
    ├── 0000/   ← 第1次全盘扫描开始（极北纬度）
    ├── 0002/   ← 同一次扫描，中纬度
    ├── 0005/   ← 同一次扫描，赤道偏北
    ├── 0007/   ← 同一次扫描，新加坡纬度 ⬅
    ├── 0010/   ← 第2次全盘扫描开始
    ├── 0012/   ...
    └── ...
```

> [!IMPORTANT]
> 目录名不是整 10 分钟间隔，而是**卫星逐行扫描的精确开始时间**。Himawari-9 从北到南扫描整个地球圆盘需 ~10 分钟，不同纬度的数据落在不同子目录中。每个子目录下有 ~1408 个文件（16 波段 × 88 tiles）。

### 我们提取什么

每次扫描（10 分钟），我们只下载 **1 个文件**：

```
OR_HFD-005-B13-M1C13-T036_GH9_sYYYYDDD...nc  (~3MB)
                    ↑         ↑
                Band 13    Tile 036 (新加坡)
```

流程：下载 `.nc` → netCDF4 提取 TBB → 裁剪 128×128 → 保存为 `.npy` (~64KB)

---

## 下载管道架构

```mermaid
graph LR
    A["NOAA S3<br/>noaa-himawari9"] -->|"aws s3 cp<br/>--no-sign-request"| B["Download Server<br/>13.214.215.64"]
    B -->|"处理: .nc → .npy"| C["Our S3<br/>weather-ai-models"]
    C -->|"sync_satellite_data"| D["API Server<br/>3.0.28.161"]
    D -->|"npy → PNG 转换"| E["前端<br/>/satellite/frames"]
```

### 三个线程

| 线程 | 功能 | 频率 |
|------|------|------|
| **RealTime** | 下载最新帧 | 每 10 分钟 |
| **Backfill** | 4 进程并行回填历史数据 | 持续 |
| **GovData** | 同步传感器数据 (温度/降雨/湿度/PM2.5) | 每 4 小时 |

### 回填完整性检查

- 每天 144 帧全部上传后，写入 `.complete` marker 到 S3
- `check_s3_exists` 检查 marker 是否存在决定是否跳过
- 被中断的不完整日期会自动重新处理补全

### 年度通知

回填跨入新年份时，通过 SNS 发送邮件汇报（天数/帧数/失败/跳过）。

---

## 文件命名与时区

```
SAT_128_20230101_0800.npy
 ↑   ↑      ↑       ↑
 |  分辨率  日期   SGT时间
 卫星标识
```

> [!WARNING]
> 文件名使用 **SGT (UTC+8)** 时间！在 API 端 cleanup 和比较时需 `-8h` 转 UTC。

---

## 关键配置

| 参数 | 位置 | 值 |
|------|------|-----|
| `START_DATE` | systemd service | `2023-01-01` |
| `PARALLEL_JOBS` | `.env` | `4` |
| `CHECK_INTERVAL_REALTIME` | systemd service | `600` (10 min) |
| `SNS_TOPIC_ARN` | 代码默认 | `arn:aws:sns:ap-southeast-1:...:weather-ai-download-complete` |

### 日志位置

```
/home/ubuntu/weather-ai/logs/download_manager.log
```
（注意：不是 `journalctl`，是文件输出）

---

## API 端云图展示

| 指标 | 值 |
|------|-----|
| 端点 | `/satellite/frames` |
| 帧数 | 全天 144 帧 |
| 格式 | base64 PNG (512×512 RGBA) |
| 响应大小 | ~12.5 MB |
| 响应时间 | ~0.67 秒 |
| 预渲染 | `.npy` → `.png` 本地转换 (`processed_data/png/`) |
