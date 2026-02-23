# Weather AI Model Tuning Log

## 2026-02-23: Yearly Incremental Training Results & Data Pipeline Analysis

### 1. Training Overview

| Item | Value |
|------|-------|
| Server | `54.179.62.87` (g4dn.xlarge, Tesla T4) |
| Duration | 01:20 → 06:55 SGT (~5.5h) |
| Strategy | Yearly incremental: 2020→2026, initial 30 epochs + incremental 10 epochs |
| Model | `WeatherFusionNet` (sensor + satellite fusion) |

### 2. Per-Year Evaluation

| Year | Sensor Size | Rows | F1 Score | Accuracy | Best Threshold | Rain Ratio |
|------|------------|------|----------|----------|---------------|------------|
| 2020 | 167 MB | 3.2M | 34.7% | 16.7% | 1.00 | 4.1% |
| 2021 | 184 MB | 3.2M | 33.0% | 16.4% | 1.07 | 3.9% |
| 2022 | 188 MB | 3.2M | **37.2%** | 15.7% | 0.86 | 4.1% |
| 2023 | 175 MB | 3.1M | 34.0% | 19.3% | 0.85 | 4.3% |
| 2024 | 160 MB | 3.2M | 35.8% | 5.3% | 1.02 | 4.0% |
| 2025 | 150 MB | 3.1M | **41.8%** 🏆 | 38.5% | 0.79 | 4.4% |
| 2026 | 17 MB | 0.3M | 29.4% | 30.3% | 1.51 | 1.1% |

> [!IMPORTANT]
> 2025 model selected as `latest.pth` — best overall F1 (41.8%). 2026 degraded due to insufficient data (only ~2 months, 1.1% rain ratio).

### 3. Data Pipeline Discrepancy (Mac vs Server)

> [!WARNING]
> Two independent data pipelines produce different sensor granularity, directly affecting training data volume and potentially model quality.

#### Mac Pipeline: [fetch_and_process_gov_data.py](file:///Users/jinhui/development/tools/claude-skill/services/download/fetch_and_process_gov_data.py)

- **Data source**: Direct API calls to `api.data.gov.sg`
- **Granularity**: **1-minute** (raw API resolution)
- **Processing**: `pivot_table` on raw data, no resampling
- **Output**: ~956万 rows/year, ~524 MB

#### Server Pipeline: [process_gov_data_from_s3.py](file:///Users/jinhui/development/tools/claude-skill/services/training/process_gov_data_from_s3.py)

- **Data source**: S3 govdata JSON (pre-downloaded)
- **Granularity**: **10-minute** (resampled)
- **Processing**: `dt.floor('10min')` groupby aggregation
  - Rainfall: `sum` (累加 10 分钟内的降雨量)
  - Other metrics: `mean` (取 10 分钟均值)
- **Output**: ~306万 rows/year, ~150 MB

```diff
 # process_gov_data_from_s3.py (server) — lines 142-153
+    # 10 分钟重采样：减少数据量 ~75%，避免训练时重复计算
+    df['ts_bucket'] = df['timestamp'].dt.floor('10min')
+    agg_dict = {col: ('sum' if col == 'rainfall' else 'mean')
+                for col in DATA_TYPES}
+    resampled = df.groupby(['ts_bucket', 'sensor_id']).agg(agg_dict).reset_index()
```

#### Why 10-Minute Resampling Was Introduced

1. **Satellite alignment**: Himawari-9 produces frames every 10 minutes. The training code ([weather_dataset.py:175](file:///Users/jinhui/development/tools/claude-skill/services/training/weather_dataset.py#L175)) assumes `Sensor data is already resampled to 10-min`.
2. **Memory efficiency**: ~75% less data to load per year.
3. **Redundancy removal**: 1-minute sensor readings between satellite frames contribute no additional satellite context.

#### Impact on Model Quality

Unclear at this point. Key considerations:
- Mac training used 1-min data → `WeatherDataset` grouped multiple sensor rows to the same satellite frame anyway
- Server training used 10-min data → cleaner alignment but lost intra-10-min variance
- The rainfall **sum** aggregation means 10-min totals are higher individual values than 1-min readings, changing the effective distribution

### 4. Current Issues

1. **Low F1 across all years** (29-42%) — model struggles with rain detection (high false positive rate)
2. **Extreme class imbalance** — only ~4% rain samples despite `WeightedRandomSampler` and `WeightedMSELoss`
3. **Regression vs Classification** — current MSE regression may not suit binary rain/no-rain discrimination. Diagnostic recommends `BCELoss + Sigmoid`.

### 5. Next Steps (TODO)

- [ ] Add model selection gate to `train_yearly.sh`: only update `latest.pth` if F1 improves
- [ ] Investigate whether 1-min vs 10-min sensor data affects F1
- [ ] Consider switching to classification head (BCELoss) for rainfall prediction
- [ ] Evaluate longer training epochs (current: 30 initial + 10 incremental)
