#!/usr/bin/env python3
"""
API 服务器启动入口。

WorkingDirectory 保持在 services/api/（数据文件所在路径），
通过 sys.path 让 Python 找到 backend/ 下的模块。

启动前自动从 S3 govdata 同步最近 N 天传感器数据并生成 CSV。
"""
import sys
import os
import logging

# 将 backend/ 加入 Python 模块搜索路径
backend_dir = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend_dir)

# 启动前：同步传感器数据
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("startup")

try:
    from sensor_data_manager import SensorDataManager
    manager = SensorDataManager(base_dir=os.path.dirname(__file__))
    csv_path = manager.run()
    logger.info(f"Sensor data ready: {csv_path}")
except Exception as e:
    # 传感器同步失败不应阻止 API 启动（可用旧 CSV 或实时采集）
    logger.error(f"Sensor data sync failed (non-fatal): {e}")

# 启动 FastAPI 应用
from api import app  # noqa: E402

if __name__ == "__main__":
    import uvicorn
    workers = 2
    for i, arg in enumerate(sys.argv):
        if arg == "--workers" and i + 1 < len(sys.argv):
            workers = int(sys.argv[i + 1])
    uvicorn.run("start:app", host="0.0.0.0", port=8000, workers=workers)
