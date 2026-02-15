# API 服务器验证报告

## 测试环境
- **API 服务器**: `http://3.0.28.161:8000`
- **模型版本**: 4D (`20260214_185536`, 278KB)
- **测试时间**: 2026-02-15 21:36 SGT

## 端点测试结果

| 端点 | 状态 | 响应 |
|------|------|------|
| `/health` | ✅ 200 | `v0.9.0`, geocoding: onemap |
| `/predict?lat=1.35&lon=103.82` (City) | ✅ 200 | 17.5mm Heavy Rain, station: Lornie Road |
| `/predict` (Changi) | ✅ 200 | 3.72mm Heavy Rain |
| `/predict` (Jurong) | ✅ 200 | 3.72mm Heavy Rain |
| `/predict` (Woodlands) | ✅ 200 | 3.72mm Heavy Rain |

## 模型加载

```
Loading Model...
Model loaded successfully.  ✅
```

## 非致命 Warning (已有)

| Warning | 影响 | 建议 |
|---------|------|------|
| `search_history has no column named response_time_ms` | DB schema 不匹配 | 需要 migration 添加列 |
| `OneMap Token unavailable` | 地理编码降级为 Nominatim | 检查 OneMap API 凭证 |
| `Structured DB write failed: NoneType.isoformat` | 数据记录缺失 | 检查 `forecast_result` 写入逻辑 |

## 操作记录

1. `predict.py` 回退: `sensor_features=7` → `4`, 移除 wind 特征处理
2. 从 S3 恢复 4D 模型 `20260214_185536` (278KB)
3. 7D 模型已归档: `s3://…/models/model-7d-20260215-2130.pth` (502KB)
