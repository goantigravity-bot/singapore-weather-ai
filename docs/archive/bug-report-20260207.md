# Bug Report — 2026-02-07

## 训练 0.1 秒完成，模型无实际学习

**发现时间**: 2026-02-07  
**严重程度**: Critical  
**状态**: ✅ 已修复  

---

### 现象

训练调度器报告每批次在 **0.1 秒**完成，`training_metrics.json` 显示 MAE/RMSE 为 0。模型没有实际学习。

### 根因分析

发现 **7 个 bug**，共同导致训练无效或监控信息不准确：

| # | Bug | 文件 | 影响 |
|---|-----|------|------|
| 1 | 传感器数据来源错误 | `train_rolling_window.py` | 调用 `fetch_and_process_gov_data.py`（NEA API 返回 2026-01 数据），而非使用调度器已下载的 govdata JSON（2025-10 数据）|
| 2 | 循环条件 off-by-one | `train_rolling_window.py` | `while current_start < end_date`，当 `--start == --end`（单日训练）时循环不执行，**整个训练流程被跳过** |
| 3 | PyTorch 兼容性 | `train.py` | `ReduceLROnPlateau(verbose=True)` 在新版 PyTorch 2.x 中已移除 |
| 4 | S3 sync warning 误判 | `training_scheduler.py` | `aws s3 sync` 遇到临时文件产生 warning + 非零 exit code，被误判为下载失败 |
| 5 | 冗余 JAXA FTP 下载 | `train_rolling_window.py` | 调度器已从 S3 下载完数据，但 `train_rolling_window.py` 再次从 JAXA FTP 逐个下载 ~700MB 的 .nc 文件，导致训练卡在慢速 FTP |
| 6 | 邮件通知 epoch 数硬编码 | `notification.py` / `training_scheduler.py` | 邮件显示 epochs=100，但实际因 Early Stopping 仅训练 10 个 epoch；状态累计 epochs 也使用硬编码 100 |
| 7 | 训练日志缓冲延迟 | `train_rolling_window.py` | `train.py` 作为子进程运行时 stdout 被缓冲，epoch 日志在训练全部完成后才输出，无法实时监控 |

### 修复详情

#### Bug 1: 传感器数据来源
```diff
 # train_rolling_window.py
-cmd_sensor = f"export FETCH_START_DATE={s_str} && export FETCH_END_DATE={e_str} && python3 fetch_and_process_gov_data.py"
+cmd_sensor = "python3 convert_govdata_to_csv.py"
```
**原因**: `fetch_and_process_gov_data.py` 的 `FETCH_CONFIG` 硬编码 2026-01 日期，且 NEA API 不返回 3 个月前的历史数据。`convert_govdata_to_csv.py` 直接从调度器已下载的本地 JSON 生成 CSV，天然与卫星日期对齐。

#### Bug 2: 循环条件
```diff
 # train_rolling_window.py
-while current_start < end_date:
+while current_start <= end_date:
```
**原因**: 调度器传入 `--start 2025-10-01 --end 2025-10-01`（单日批次），`<` 条件导致循环体完全不执行。

#### Bug 3: PyTorch verbose 参数
```diff
 # train.py
-scheduler = optim.lr_scheduler.ReduceLROnPlateau(..., verbose=True)
+scheduler = optim.lr_scheduler.ReduceLROnPlateau(...)
```

#### Bug 4: S3 warning 容错
```diff
 # training_scheduler.py - download_from_s3()
 if result.returncode != 0:
-    logger.error(f"卫星数据下载失败: {result.stderr.decode()}")
-    return False
+    stderr = result.stderr
+    if "Skipping file" in stderr and "error" not in stderr.lower():
+        logger.warning(f"非致命警告（已忽略）: {stderr.strip()}")
+    else:
+        logger.error(f"卫星数据下载失败: {stderr}")
+        return False
```

#### Bug 5: 移除冗余 FTP 下载
```diff
 # train_rolling_window.py — 移除步骤 2（JAXA FTP 下载）和步骤 3（预处理）
-cmd_sat = f"python3 download_jaxa_data.py --mode batch --start {s_str} --end {e_str}"
-cmd_pre = "python3 preprocess_images.py"
+# 2 & 3: 卫星数据下载和预处理已由 training_scheduler.py 完成
```

#### Bug 6: 邮件 epoch 数硬编码
```diff
 # notification.py
-<li><strong>Epochs:</strong> {metrics.get('epochs', 100)}</li>
+<li><strong>Epochs:</strong> {metrics.get('epochs', 'N/A')}</li>

 # training_scheduler.py - send_notification()
-metrics = {"date": date_str, "mae": 0.0, "rmse": 0.0, "accuracy": 0.0}
+metrics = {"date": date_str, "mae": 0.0, "rmse": 0.0, "accuracy": 0.0, "epochs": 0}
+metrics["epochs"] = data.get("final_epoch", 0)

 # training_scheduler.py - 状态累加
-state["total_epochs"] += EPOCHS_PER_BATCH  # 硬编码 100
+actual_epochs = m.get("final_epoch", EPOCHS_PER_BATCH)  # 从实际训练结果读取
+state["total_epochs"] += actual_epochs
```
**原因**: `notification.py` 默认值 `100`，`training_scheduler.py` 使用 `EPOCHS_PER_BATCH=100` 常量而非从 `training_metrics.json` 读取实际训练 epoch 数（Early Stopping 后实际仅 10 个 epoch）。

#### Bug 7: 训练日志缓冲延迟
```diff
 # train_rolling_window.py
-cmd_train = f"export EPOCHS_INITIAL=... && python3 train.py"
+cmd_train = f"export EPOCHS_INITIAL=... && export PYTHONUNBUFFERED=1 && python3 train.py"
```
**原因**: Python 子进程默认缓冲 stdout，导致 `train.py` 的 epoch 日志在训练全部完成后才输出到 `training_scheduler.log`，无法实时监控。

### 附带改进

| 项目 | 变更 |
|------|------|
| `training_scheduler.py` | `.complete` 标记依赖改为检查实际 `.nc` 文件 |
| `training_scheduler.py` | 移除 S3 归档步骤（每批次节省 ~4 分钟） |
| `training_scheduler.py` | `cleanup_raw_data()` 增加 `processed_data/*.npy` 清理 |
| `train_rolling_window.py` | 添加 `PYTHONUNBUFFERED=1` 实现 epoch 日志实时输出 |
| `monitor_api.py` | 移除 50 天显示限制，`totalDays` 动态计算 |

### 验证结果

```
修复前: Training Complete in 0.1s  (0 batches, 0 samples)
修复后: Training Complete in 270s (547 batches, 10 epochs)
        Epoch [1/10] Time: 27.4s | Loss: 0.4296 | Val Loss: 0.1348
        Epoch [2/10] Time: 26.1s | Loss: 0.4103 | Val Loss: 0.1685
        Epoch [3/10] Time: 25.2s | Loss: 0.3990 | Val Loss: 0.1543
```

### 经验教训

1. **数据流水线要端到端对齐** — 下载和训练两个阶段的数据源必须一致（S3 vs API），否则时间窗口不匹配
2. **边界条件测试** — `start == end` 是常见边界用例，循环条件必须覆盖
3. **子进程错误处理不能简单看 exit code** — `aws s3 sync` 的 warning 也会导致非零退出码
4. **避免流水线中的冗余步骤** — 调度器已处理的步骤不应在子脚本中重复
5. **避免硬编码默认值** — 尤其是动态数值（如 epoch 数），应从实际运行结果读取
6. **子进程输出需禁用缓冲** — `PYTHONUNBUFFERED=1` 或 `-u` 确保日志实时可见

