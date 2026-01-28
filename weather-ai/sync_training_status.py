#!/usr/bin/env python3
"""
训练状态同步到 S3 - 用于监控仪表盘
在每个关键阶段调用此模块上传状态
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

S3_BUCKET = "weather-ai-models-de08370c"
STATUS_KEY = "status/training_status.json"
LOCAL_STATUS = Path.home() / "weather-ai" / "training_status.json"

def sync_status_to_s3(
    current_date: str = None,
    current_phase: str = "idle",
    phases: list = None,
    completed_batches: int = 0,
    total_epochs: int = 0,
    status: str = "running",
    disk_usage: str = None,
    message: str = None
):
    """上传训练状态到 S3"""
    
    if phases is None:
        phases = [
            {"name": "下载数据", "status": "pending", "progress": None},
            {"name": "预处理", "status": "pending", "progress": None},
            {"name": "训练", "status": "pending", "progress": None},
            {"name": "同步模型", "status": "pending", "progress": None}
        ]
    
    status_data = {
        "currentDate": current_date,
        "currentPhase": current_phase,
        "phases": phases,
        "completedBatches": completed_batches,
        "totalEpochs": total_epochs,
        "status": status,
        "diskUsage": disk_usage,
        "message": message,
        "lastUpdate": datetime.now().isoformat()
    }
    
    # 保存本地
    LOCAL_STATUS.write_text(json.dumps(status_data, indent=2, ensure_ascii=False))
    
    # 上传到 S3
    try:
        result = subprocess.run([
            "aws", "s3", "cp",
            str(LOCAL_STATUS),
            f"s3://{S3_BUCKET}/{STATUS_KEY}"
        ], capture_output=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        print(f"状态同步失败: {e}")
        return False

def update_phase(phase_index: int, status: str, progress: int = None, message: str = None):
    """更新特定阶段的状态"""
    try:
        if LOCAL_STATUS.exists():
            data = json.loads(LOCAL_STATUS.read_text())
            if 0 <= phase_index < len(data.get("phases", [])):
                data["phases"][phase_index]["status"] = status
                data["phases"][phase_index]["progress"] = progress
                data["phases"][phase_index]["message"] = message
                data["lastUpdate"] = datetime.now().isoformat()
                LOCAL_STATUS.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                
                # 上传到 S3
                subprocess.run([
                    "aws", "s3", "cp",
                    str(LOCAL_STATUS),
                    f"s3://{S3_BUCKET}/{STATUS_KEY}"
                ], capture_output=True, timeout=30)
                return True
    except Exception as e:
        print(f"阶段更新失败: {e}")
    return False

if __name__ == "__main__":
    # 测试
    sync_status_to_s3(
        current_date="2025-10-01",
        current_phase="training",
        completed_batches=0,
        total_epochs=0,
        phases=[
            {"name": "下载数据", "status": "completed", "progress": 100},
            {"name": "预处理", "status": "completed", "progress": 100},
            {"name": "训练", "status": "running", "progress": 50},
            {"name": "同步模型", "status": "pending", "progress": None}
        ]
    )
    print("状态已同步到 S3")
