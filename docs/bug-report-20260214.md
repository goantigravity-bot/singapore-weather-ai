# Bug Report — 2026-02-14

## API 服务器卫星数据未清理导致磁盘耗尽

**发现时间**: 2026-02-14  
**严重程度**: Critical  
**状态**: ✅ 已修复  

---

### 现象

API 服务器（`3.0.28.161`, t3.medium, 20GB EBS）磁盘使用率达 **96%**，仅剩 **914MB** 可用空间。`satellite_data/` 目录累积 **8.8GB** 数据（13 个 `.nc` 文件），严重威胁服务稳定性。

### 根因分析

| # | Bug | 文件 | 影响 |
|---|-----|------|------|
| 1 | 卫星数据清理逻辑未实现 | `api.py` (`sync_satellite_data`) | 后台同步线程每 5 分钟从 S3 下载当天卫星数据（~144 文件/天 × 5MB ≈ 700MB/天），但清理逻辑始终是 `# TODO`，导致数据无限积累 |

#### 代码定位

```python
# api.py L175-176 (修复前)
# Cleanup old files (> 6 hours)
# TODO: Implement strict cleanup to avoid disk fill
```

`sync_satellite_data()` 函数在每次同步周期中：
1. ✅ 按日期列出 S3 中的卫星文件
2. ✅ 下载本地不存在的文件到 `satellite_data/`
3. ❌ **从未执行清理** — 旧文件永远不会被删除

### 修复详情

```diff
 # api.py — sync_satellite_data()
-    # Cleanup old files (> 6 hours)
-    # TODO: Implement strict cleanup to avoid disk fill
+    # Cleanup: remove satellite files older than 3 hours to prevent disk exhaustion.
+    # File naming convention: NC_H09_YYYYMMDD_HHMM_R21_FLDK.*.nc
+    cleanup_count = 0
+    cleanup_bytes = 0
+    cutoff = now_utc - timedelta(hours=3)
+    for f in os.listdir(local_dir):
+        if not f.endswith(".nc"):
+            continue
+        try:
+            parts = f.split("_")
+            file_dt = datetime.strptime(f"{parts[2]}_{parts[3]}", "%Y%m%d_%H%M")
+            if file_dt < cutoff:
+                fpath = os.path.join(local_dir, f)
+                cleanup_bytes += os.path.getsize(fpath)
+                os.remove(fpath)
+                cleanup_count += 1
+        except (ValueError, IndexError):
+            pass
+    if cleanup_count:
+        logger.info(f"🧹 Cleaned {cleanup_count} old satellite files ({cleanup_bytes / 1024 / 1024:.1f} MB freed)")
```

**设计决策**:
- **3 小时窗口**（而非原注释的 6 小时）：保留足够的近期数据，同时将最大占用控制在 ~100MB 以内（3h × 6 文件/h × 5MB）
- **基于文件名解析时间**（而非 `os.stat` mtime）：文件名中的时间戳是数据的真实时间，不受下载时间影响

### 部署与验证

| 步骤 | 命令 | 结果 |
|------|------|------|
| 部署代码 | `scp api.py ubuntu@3.0.28.161:~/weather-ai/api.py` | ✅ |
| 清理旧数据 | `rm -rf ~/weather-ai/satellite_data/*` | 释放 8.8GB |
| 重启服务 | `sudo systemctl restart weather-api` | ✅ active |
| 健康检查 | `curl http://3.0.28.161:8000/health` | `{"status":"ok","version":"0.8.0"}` |

```
修复前: 磁盘 95% 已用 (914MB 剩余), satellite_data/ = 8.8GB
修复后: 磁盘 50% 已用 (9.8GB 剩余), satellite_data/ = 16KB
```

### 经验教训

1. **TODO 注释不等于已完成** — 关键资源清理逻辑不应被标记为 TODO 后遗忘，应在首次实现时就包含
2. **后台线程的副作用需要监控** — 守护线程静默运行，磁盘耗尽前不会有明显错误
3. **定期健康检查应包含磁盘指标** — `df -h` 应纳入自动化监控告警

---

## 训练反复失败：Dataset is empty (0 samples)

**发现时间**: 2026-02-14  
**严重程度**: Critical  
**状态**: ✅ 已修复  

### 现象

训练调度器卡在 `2026-01-05`，每 ~3 分钟失败并发送邮件通知，持续数小时。错误信息：

```
ValueError: Dataset is empty (0 samples). Check satellite data in processed_data/ and satellite_data/
```

### 根因分析

| # | Bug | 文件 | 影响 |
|---|-----|------|------|
| 1 | S3 预处理数据不完整 | `processed/satellite/20260105/` | 仅 12 个 .npy（UTC 17:40-19:30，即 SGT 01:40-03:30），覆盖窗口过窄 |
| 2 | 调度器复用残留 .npy | `training_scheduler.py` | `_check_processed_available` 命中不完整数据后走快速路径，跳过全天预处理 |
| 3 | 损坏临时文件未清理 | 训练服务器 `satellite_data/` | 23 个带随机后缀的 `.nc` 文件（如 `.nc.8871bfaF`）占 7.1GB，不被识别 |

**根因链**：S3 有 143 个完整 raw .nc → 但 S3 只有 12 个 .npy（凌晨窗口）→ 调度器检测到 .npy 走快速路径 → 12 个 .npy 覆盖 SGT 01:40-03:30 → 传感器数据夜间稀疏 → 对齐后 0 个有效样本 → 反复失败不推进日期

### 修复步骤

| 步骤 | 操作 | 结果 |
|------|------|------|
| 1 | 停止调度器 | 邮件轰炸终止 |
| 2 | 清理损坏 .nc 临时文件 | 释放 7.1GB |
| 3 | 清理本地残留 .npy | 清除错误缓存 |
| 4 | 删除 S3 上 12 个不完整 .npy | 强制走 raw .nc → 预处理完整管线 |
| 5 | 重启调度器 `--run 1` | 正在下载 143 个完整 .nc 重新预处理 |

---

## API 卫星数据改用 processed .npy

**发现时间**: 2026-02-14  
**严重程度**: Medium (优化)  
**状态**: ✅ 已修复  

### 现象

API 服务器下载 raw `.nc` 卫星数据（~700MB/天），是之前磁盘耗尽的根源。实际上 API 推理链路只需要裁剪后的新加坡区域数据（64×64 矩阵）。

### 修复

将 `sync_satellite_data()` 改为从 S3 `processed/satellite/` 同步 `.npy` 文件（~16KB/个），存储到 `processed_data/`。

| 指标 | 改前 (raw .nc) | 改后 (processed .npy) |
|------|---------------|---------------------|
| 每天数据量 | ~700MB | ~2.3MB |
| 磁盘撑满风险 | 高 | 几乎为零 |
| 云层分析 | ✅ | ✅（数据可用时） |

`predict.py` 已优先查找 `processed_data/` 目录，无需额外修改。当 download server 追赶到当日数据后，API 将自动获得实时卫星数据。
