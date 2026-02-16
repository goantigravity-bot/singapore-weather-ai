# Weather AI v0.6 — 训练性能优化 Walkthrough

> 日期: 2026-02-07  
> 版本: v0.6  
> 目标: 通过纯代码优化将 AWS 训练时间从 ~11 小时/批次降至 ~15-40 分钟/批次

---

## 1. 背景 & 问题分析

### 当前性能基线（AWS EC2 CPU 实例）

| 指标 | 实测值 |
|------|--------|
| 设备 | CPU（t3 系列, 无 GPU） |
| 每批次训练 | **~11-12 小时** |
| 每 epoch 耗时 | **~13.4 分钟** |
| Epochs 配置 | 50（增量训练也被设为 50） |
| 数据量 | 595K-689K 条传感器记录 |
| 已完成批次 | 23 天 (2025-10-01 → 10-23) |
| 剩余批次 | ~97 天 |
| 预计剩余运行时间 | **~48 天连续运行** |

### 根本原因

1. **EPOCHS_INCREMENTAL=50**：增量训练与首次训练使用相同 epochs，但实际日志显示 **Epoch 1 就已收敛**
2. **无 Early Stopping**：val_loss 不再下降后仍固定跑完所有 epochs，49 个 epoch 约 98% 时间被浪费
3. **磁盘 IO 瓶颈**：`__getitem__` 每次调用都做 `glob()` + `np.load()` 磁盘读取
4. **单线程数据加载**：`DataLoader` 使用 `num_workers=0`，主线程串行加载

---

## 2. 优化方案

### Level 0 — 紧急修复（一行改动，立省 90%）

#### [train_rolling_window.py](file:///Users/jinhui/development/tools/claude-skill/train_rolling_window.py)

**改动**：`EPOCHS_INCREMENTAL` 从 `args.epochs`（50）改为 `max(5, args.epochs // 10)`

```diff
-cmd_train = f"export EPOCHS_INITIAL={args.epochs} && export EPOCHS_INCREMENTAL={args.epochs} && python3 train.py"
+incremental_epochs = max(5, args.epochs // 10)
+cmd_train = f"export EPOCHS_INITIAL={args.epochs} && export EPOCHS_INCREMENTAL={incremental_epochs} && python3 train.py"
```

**效果**：增量训练从 50 epochs → 5 epochs，训练时间 11 小时 → ~1.3 小时

---

### Level 1 — 代码优化

#### [train.py](file:///Users/jinhui/development/tools/claude-skill/train.py) — 训练循环全面升级

| 优化项 | 实现方式 | 效果 |
|--------|----------|------|
| **Early Stopping** | `patience=3`，val_loss 连续 3 epoch 不改善就终止 | 避免无效迭代，实际可能 1-3 epoch 就终止 |
| **LR Scheduler** | `ReduceLROnPlateau(factor=0.5, patience=2, min_lr=1e-6)` | val_loss 停滞时自动衰减学习率，帮助精细收敛 |
| **动态 Batch Size** | CUDA=32, MPS=16, CPU=8 | GPU 吞吐量提升，CPU 迭代次数减半 |
| **Mixed Precision (AMP)** | `autocast + GradScaler`（仅 CUDA 生效） | GPU 训练加速 ~2x，显存减半 |
| **训练计时** | `time.time()` 记录到 `training_metrics.json` | 追踪优化效果 |
| **logging 替代 print** | `logging.getLogger()` | 符合项目日志规范 |

**关键代码变更**：

```python
# Early Stopping
EARLY_STOPPING_PATIENCE = int(os.environ.get('EARLY_STOPPING_PATIENCE', 3))
no_improve_count = 0

# LR Scheduler
scheduler = optim.lr_scheduler.ReduceLROnPlateau(
    optimizer, mode='min', factor=0.5, patience=2, min_lr=1e-6, verbose=True
)

# AMP (仅 CUDA 设备)
use_amp = (DEVICE.type == 'cuda')
scaler = GradScaler(enabled=use_amp)

# 训练循环中
with autocast(device_type=DEVICE.type, enabled=use_amp):
    outputs = model(sat, sensor)
    loss = criterion(outputs, target)

scaler.scale(loss).backward()
scaler.step(optimizer)
scaler.update()
scheduler.step(avg_val_loss)

# Early Stop 判断
if no_improve_count >= EARLY_STOPPING_PATIENCE:
    break
```

**新增 metrics 输出字段**：
- `training_time_seconds`: 训练耗时（秒）
- `early_stopped`: 是否被 Early Stopping 终止
- `max_epochs`: 配置的最大 epochs
- `final_epoch`: 实际执行的 epochs
- `device`: 训练设备
- `batch_size`: 实际 batch size

---

#### [weather_dataset.py](file:///Users/jinhui/development/tools/claude-skill/weather_dataset.py) — 数据加载优化

| 优化项 | Before | After |
|--------|--------|-------|
| **卫星数据读取** | `glob()` + `np.load()` 每次磁盘 IO | `self._sat_cache` 内存字典 O(1) 查找 |
| **DataLoader workers** | `num_workers=0`（串行） | `num_workers=4`（并行预取） |
| **pin_memory** | 无 | `True`（加速 CPU→GPU 传输） |
| **persistent_workers** | 无 | `True`（避免每 epoch 重建进程） |

**关键代码变更**：

```python
# __init__: 一次性预加载到内存
self._sat_cache = {}
for f in os.listdir(processed_dir):
    if f.endswith(".npy"):
        self._sat_cache[ts_str] = np.load(os.path.join(processed_dir, f))

# __getitem__: O(1) 内存查找
data = self._sat_cache.get(utc_str)

# DataLoader: 多线程预取
DataLoader(dataset, num_workers=4, pin_memory=True, persistent_workers=True)
```

---

## 3. 预期效果对比

| 场景 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 增量 Epochs | 50 | 5 (Early Stop 可能 1-3) | **10-50x** |
| 每批次训练 | ~11 小时 | ~15-40 分钟 | **17-44x** |
| 每 epoch 数据加载 | 磁盘 IO | 内存读取 | **~15x** |
| 97 天总训练时间 | ~48 天 | ~1-3 天 | **16-48x** |

---

## 4. 部署步骤

1. 将以下 3 个文件同步到 AWS 训练服务器：
   - `train.py`
   - `weather_dataset.py`
   - `train_rolling_window.py`

2. 确认 PyTorch 版本 ≥ 2.0（支持 `torch.amp`）

3. 重启训练调度器，观察日志确认：
   - `EPOCHS_INCREMENTAL` 显示为 5（而非 50）
   - `Early Stop patience=3` 出现在训练配置中
   - `AMP (Mixed Precision): False`（CPU 模式预期为 False）
   - 每 epoch 日志末尾显示 `LR:` 和 `Time:` 信息

---

## 5. 后续优化（Level 3 — GPU 加速）

> 等 Level 1 在 AWS 上跑一天观察效果后，再决定是否需要 GPU 升级。

若需要进一步加速：
- **方案 A**：申请 EC2 GPU 配额 → `g4dn.xlarge` Spot 实例
- **方案 B**：使用 SageMaker 托管训练（独立 GPU 配额）
- **预期效果**：GPU 模式下 AMP + Batch=32 可再提升 5-10x
