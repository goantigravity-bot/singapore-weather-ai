#!/usr/bin/env python3
"""
手动添加训练记录
用于补充刚才完成的训练
"""
from datetime import datetime, timedelta
from training_history import add_training_record

# 刚才的训练信息
start_time = datetime(2026, 1, 25, 21, 8, 40)
end_time = datetime(2026, 1, 25, 22, 2, 48)
duration = (end_time - start_time).total_seconds()

metrics = {
    'mae': 0.0704,
    'rmse': 0.8568,
    'accuracy': 0.9765,
    'threshold': 0.1,
    'num_samples': 222
}

data_info = {
    'satellite_files': 140,
    'sensor_records': 230713,
    'num_sensors': 61,
    'date_range': '2026-01-01 至 2026-01-21'
}

training_config = {
    'epochs': 30,
    'batch_size': 4,
    'learning_rate': 0.001,
    'device': 'MPS (Apple Silicon)'
}

record = add_training_record(
    start_time=start_time,
    end_time=end_time,
    duration_seconds=duration,
    metrics=metrics,
    data_info=data_info,
    training_config=training_config,
    success=True
)

print("✅ 训练记录已添加")
print(f"ID: {record['id']}")
print(f"时间: {record['start_time']} - {record['end_time']}")
print(f"耗时: {record['duration_formatted']}")
print(f"MAE: {metrics['mae']:.4f} mm")
print(f"准确率: {metrics['accuracy']*100:.2f}%")
