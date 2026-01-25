# 训练性能优化计划

## 📋 当前问题

### 训练时间过长
- **当前**: 230K记录 × 30 epochs = 45-60分钟
- **未来**: 随着数据增长，时间会线性增加
  - 1个月后: ~680K记录 → 2-3小时
  - 3个月后: ~1.6M记录 → 5-7小时

### 数据增长预测
- 每日新增: ~10,000-15,000条记录
- 每月新增: ~450,000条记录
- 无限制增长会导致训练不可行

---

## 🎯 优化方案

### 方案1: 滑动窗口（推荐 ⭐）

**实施位置**: `weather_dataset.py`

**原理**: 只保留最近N天的数据用于训练

**代码修改**:
```python
# 在 WeatherDataset.__init__ 中添加
MAX_TRAINING_DAYS = 30  # 只使用最近30天数据

# 过滤数据
df['timestamp'] = pd.to_datetime(df['timestamp'])
cutoff_date = df['timestamp'].max() - timedelta(days=MAX_TRAINING_DAYS)
df = df[df['timestamp'] >= cutoff_date]

print(f"使用滑动窗口: 最近{MAX_TRAINING_DAYS}天数据")
print(f"数据范围: {df['timestamp'].min()} 至 {df['timestamp'].max()}")
print(f"记录数: {len(df):,}")
```

**效果**:
- 数据量稳定在 ~300K 记录
- 训练时间稳定在 15-20分钟
- 模型关注最新天气模式

---

### 方案2: 减少Epochs

**实施位置**: `train.py`

**原理**: 每日训练不需要从头训练30个epochs

**代码修改**:
```python
# 修改 train.py
EPOCHS = 10  # 从30改为10

# 或者使用配置文件
EPOCHS = int(os.environ.get('TRAINING_EPOCHS', 10))
```

**效果**:
- 训练时间减少到原来的 1/3
- 对于每日增量训练足够

---

### 方案3: 增量学习（高级 ⭐⭐）

**实施位置**: `train.py`

**原理**: 使用已有模型作为起点，只微调新数据

**代码修改**:
```python
def train_model():
    # 1. Data
    print("Loading Data...")
    train_loader, val_loader = get_dataloaders(CSV_PATH, SAT_DIR, batch_size=BATCH_SIZE)
    
    # 2. Model
    model = WeatherFusionNet(sat_channels=1, sensor_features=3, prediction_dim=1)
    
    # 🆕 增量学习: 加载已有模型
    if os.path.exists(MODEL_SAVE_PATH):
        print(f"加载已有模型: {MODEL_SAVE_PATH}")
        model.load_state_dict(torch.load(MODEL_SAVE_PATH, map_location=DEVICE))
        print("使用增量学习模式（微调）")
        EPOCHS_FINE_TUNE = 5  # 微调只需要5个epochs
    else:
        print("首次训练，从头开始")
        EPOCHS_FINE_TUNE = 30  # 首次训练需要完整训练
    
    model.to(DEVICE)
    
    # 3. Loss & Optimizer
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    
    print(f"Starting Training... ({EPOCHS_FINE_TUNE} epochs)")
    
    # ... 训练循环使用 EPOCHS_FINE_TUNE
    for epoch in range(EPOCHS_FINE_TUNE):
        # ... 训练代码
```

**效果**:
- 首次训练: 30 epochs (45-60分钟)
- 后续训练: 5 epochs (7-10分钟)
- 性能提升 **6-8倍**

---

### 方案4: 输出缓冲修复

**实施位置**: `auto_train_pipeline.py`

**原理**: 强制Python实时输出，便于监控

**代码修改**:
```python
def run_command(self, cmd, step_name, timeout=3600):
    # 添加环境变量强制无缓冲输出
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
        env=env  # 🆕 添加环境变量
    )
```

**效果**:
- 训练进度实时显示在日志中
- 便于监控和调试

---

## 📊 优化效果对比

| 场景 | 当前 | 优化后 | 提升 |
|------|------|--------|------|
| 首次训练 | 45-60分钟 | 15-20分钟 | 3倍 |
| 每日训练 | 45-60分钟 | 5-10分钟 | 6-8倍 |
| 1个月后 | 2-3小时 | 5-10分钟 | 12-36倍 |
| 3个月后 | 5-7小时 | 5-10分钟 | 30-84倍 |

---

## 🔧 实施步骤

### 阶段1: 基础优化（立即可做）

1. **修改 `train.py`**
   - [ ] 减少EPOCHS到10
   - [ ] 添加增量学习逻辑

2. **修改 `weather_dataset.py`**
   - [ ] 添加滑动窗口（30天）
   - [ ] 添加数据统计输出

3. **修改 `auto_train_pipeline.py`**
   - [ ] 添加PYTHONUNBUFFERED环境变量
   - [ ] 改进日志捕获

### 阶段2: 高级优化（可选）

4. **添加配置文件**
   - [ ] 创建 `training_config.yaml`
   - [ ] 支持动态调整参数

5. **性能监控**
   - [ ] 记录每次训练时间
   - [ ] 生成性能趋势图

---

## 📝 配置建议

### 推荐配置

```python
# 训练配置
MAX_TRAINING_DAYS = 30      # 滑动窗口天数
EPOCHS_INITIAL = 30         # 首次训练epochs
EPOCHS_INCREMENTAL = 5      # 增量训练epochs
BATCH_SIZE = 4              # 批次大小
LEARNING_RATE = 1e-3        # 学习率

# 数据配置
MAX_RECORDS_PER_DAY = 15000 # 每日最大记录数（用于估算）
```

### 不同场景配置

**快速测试**:
```python
MAX_TRAINING_DAYS = 7
EPOCHS_INITIAL = 5
EPOCHS_INCREMENTAL = 2
```

**生产环境**:
```python
MAX_TRAINING_DAYS = 30
EPOCHS_INITIAL = 30
EPOCHS_INCREMENTAL = 5
```

**高精度需求**:
```python
MAX_TRAINING_DAYS = 60
EPOCHS_INITIAL = 50
EPOCHS_INCREMENTAL = 10
```

---

## ⚠️ 注意事项

1. **滑动窗口的影响**
   - 优点: 训练快，关注最新模式
   - 缺点: 丢失长期季节性模式
   - 建议: 30天足够捕捉新加坡天气模式

2. **增量学习的风险**
   - 可能导致"灾难性遗忘"
   - 建议: 每月进行一次完整重训练

3. **性能vs精度权衡**
   - 减少epochs可能略微降低精度
   - 建议: 监控评估指标，确保性能不下降

---

## 📅 实施时间表

**本次训练完成后**:
1. 实施方案1（滑动窗口）
2. 实施方案2（减少epochs）
3. 测试优化效果

**下次训练时**:
1. 实施方案3（增量学习）
2. 实施方案4（输出缓冲修复）
3. 验证性能提升

**长期**:
- 每周监控训练时间
- 每月评估模型性能
- 根据需要调整配置

---

## 📈 成功指标

- ✅ 每日训练时间 < 10分钟
- ✅ 模型性能不下降（MAE保持或改善）
- ✅ 训练时间稳定（不随数据增长而增长）
- ✅ 日志输出正常（可实时监控）

---

**创建时间**: 2026-01-25 21:58  
**状态**: 待实施  
**优先级**: 高
