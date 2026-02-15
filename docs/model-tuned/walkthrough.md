# GPU Spot 训练完成报告

## 修改的文件

| 文件 | 改动 |
|------|------|
| [training.tf](file:///Users/jinhui/development/tools/claude-skill/terraform/training.tf) | g4dn.xlarge Spot + 200GB + Deep Learning AMI |
| [process_gov_data_from_s3.py](file:///Users/jinhui/development/tools/claude-skill/services/training/process_gov_data_from_s3.py) | 增加 wind v2 API 格式解析 |
| [train_rolling_window.py](file:///Users/jinhui/development/tools/claude-skill/services/training/train_rolling_window.py) | sensor_features=7, WORK_DIR=~/training |

## 数据规模

- **传感器 CSV**: 4,094,848 行 (8 列, 含 wind_speed/wind_direction)
- **卫星 .npy**: 13,702 个 (117 天, 预处理 64×64)
- **训练集**: 644K 样本 (3.2% 雨, WeightedRandomSampler 平衡)
- **雨天**: 109 天

## 训练结果

| Epoch | Train Loss | Val Loss | Val MAE |
|-------|-----------|----------|---------|
| 1 ⭐ | 100.08 | **6.88** | 0.85 |
| 2 | 78.82 | 10.64 | 1.10 |
| 3 | 55.66 | 9.68 | 0.88 |
| 4 | 41.20 | 10.75 | 1.11 |
| 5 | 28.12 | 9.42 | 0.62 |
| 6 | 23.68 | 9.43 | 0.76 |

- Early Stop @ Epoch 6, **Best = Epoch 1** (val_loss=6.88)
- Rain accuracy: 7.4% — 模型对降雨分类能力较弱
- 模型: `s3://weather-ai-models-de08370c/models/latest.pth`

> [!WARNING]
> Val loss 从 Epoch 1 后持续升高,说明模型快速过拟合。数据量虽大(4M行),但有效的"雨天+卫星对齐"样本可能不足。后续优化方向:增加 dropout、调低 lr、增大雨天权重、或增加数据增强。

## 成本

- Spot g4dn.xlarge ≈ $0.16/hour × ~1.5h ≈ **$0.24**

## 后续步骤

1. 部署 `latest.pth` 到 API 服务器验证推理效果
2. 优化模型（增加 dropout/数据增强）提升 rain_accuracy
3. 持续采集含 wind 的传感器数据,积累后重新训练
