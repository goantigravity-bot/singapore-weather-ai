"""
monitor_api.py
监控仪表盘 API 端点

提供端到端训练管道的监控数据：
- 下载进度（FTP → S3）
- 训练进度（S3 → 预处理 → 训练）
- API 同步状态
"""

import os
import json
import subprocess
import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter
import boto3
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitor", tags=["monitor"])

# 配置
S3_BUCKET = os.environ.get("S3_BUCKET", "weather-ai-models-de08370c")
DOWNLOAD_SERVER = os.environ.get("DOWNLOAD_SERVER", "18.142.90.30")
TRAINING_SERVER = os.environ.get("TRAINING_SERVER", "46.137.236.8")

# ========================
# 数据模型
# ========================

class DownloadStatus(BaseModel):
    """下载状态"""
    currentDate: Optional[str] = None
    completedDays: int = 0
    totalDays: int = 119
    filesDownloaded: int = 0
    parallelProcesses: int = 0
    status: str = "unknown"  # running, idle, error
    lastUpdate: Optional[str] = None


class TrainingPhase(BaseModel):
    """训练阶段"""
    name: str
    status: str  # pending, running, completed, error
    progress: Optional[int] = None
    message: Optional[str] = None


class TrainingStatus(BaseModel):
    """训练状态"""
    currentDate: Optional[str] = None
    completedBatches: int = 0
    totalEpochs: int = 0
    currentPhase: str = "idle"  # downloading, preprocessing, training, syncing, idle
    phases: List[TrainingPhase] = []
    diskUsage: Optional[str] = None
    status: str = "unknown"
    lastUpdate: Optional[str] = None


class SyncStatus(BaseModel):
    """同步状态"""
    modelSynced: bool = False
    sensorDataSynced: bool = False
    lastSyncTime: Optional[str] = None
    status: str = "unknown"


class OverviewStatus(BaseModel):
    """端到端总览"""
    currentStage: str = "unknown"  # download, training, sync, idle
    download: DownloadStatus
    training: TrainingStatus
    sync: SyncStatus


# ========================
# 工具函数
# ========================

def get_s3_client():
    """获取 S3 客户端"""
    return boto3.client('s3')


def count_s3_files(prefix: str) -> int:
    """统计 S3 中的文件数"""
    try:
        s3 = get_s3_client()
        paginator = s3.get_paginator('list_objects_v2')
        count = 0
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            count += page.get('KeyCount', 0)
        return count
    except Exception as e:
        logger.error(f"Failed to count S3 files: {e}")
        return 0


def count_completed_days() -> int:
    """统计已完成的天数（通过 .complete 标记）"""
    try:
        s3 = get_s3_client()
        prefix = "satellite/"
        count = 0
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
            for obj in page.get('Contents', []):
                if obj['Key'].endswith('.complete'):
                    count += 1
        return count
    except Exception as e:
        logger.error(f"Failed to count completed days: {e}")
        return 0


def read_log_file(log_path: str, lines: int = 100) -> str:
    """读取本地日志文件"""
    try:
        if os.path.exists(log_path):
            with open(log_path, 'r') as f:
                all_lines = f.readlines()
                return ''.join(all_lines[-lines:])
        return ""
    except Exception as e:
        logger.error(f"Failed to read log file: {e}")
        return f"Error reading log: {e}"


def get_training_state() -> dict:
    """获取训练状态文件"""
    try:
        s3 = get_s3_client()
        obj = s3.get_object(Bucket=S3_BUCKET, Key="state/training_state.json")
        return json.loads(obj['Body'].read().decode('utf-8'))
    except Exception as e:
        logger.warning(f"Training state not found: {e}")
        return {}


def read_s3_log(log_key: str, lines: int = 100) -> str:
    """从 S3 读取日志文件"""
    try:
        s3 = get_s3_client()
        obj = s3.get_object(Bucket=S3_BUCKET, Key=log_key)
        content = obj['Body'].read().decode('utf-8')
        # 返回最后 N 行
        all_lines = content.split('\n')
        return '\n'.join(all_lines[-lines:])
    except Exception as e:
        logger.warning(f"Failed to read S3 log {log_key}: {e}")
        return ""


# ========================
# API 端点
# ========================

@router.get("/overview", response_model=OverviewStatus)
def get_overview():
    """获取端到端状态总览"""
    download = get_download_status()
    training = get_training_status()
    sync = get_sync_status()
    
    # 确定当前阶段
    if download.status == "running":
        current_stage = "download"
    elif training.status == "running":
        current_stage = "training"
    elif sync.lastSyncTime:
        current_stage = "idle"
    else:
        current_stage = "unknown"
    
    return OverviewStatus(
        currentStage=current_stage,
        download=download,
        training=training,
        sync=sync
    )


@router.get("/download", response_model=DownloadStatus)
def get_download_status():
    """获取下载状态"""
    try:
        # 统计已完成天数
        completed_days = count_completed_days()
        
        # 统计总文件数
        total_files = count_s3_files("satellite/")
        
        return DownloadStatus(
            completedDays=completed_days,
            totalDays=119,
            filesDownloaded=total_files,
            status="running" if completed_days < 119 else "completed",
            lastUpdate=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to get download status: {e}")
        return DownloadStatus(status="error", lastUpdate=datetime.now().isoformat())


@router.get("/training", response_model=TrainingStatus)
def get_training_status():
    """获取训练状态"""
    try:
        state = get_training_state()
        
        phases = [
            TrainingPhase(name="下载数据", status="pending"),
            TrainingPhase(name="预处理", status="pending"),
            TrainingPhase(name="训练", status="pending"),
            TrainingPhase(name="同步模型", status="pending"),
        ]
        
        current_phase = "idle"
        if state.get("waiting_for_data"):
            current_phase = "waiting"
        
        return TrainingStatus(
            currentDate=state.get("last_processed_date"),
            completedBatches=state.get("total_batches_completed", 0),
            totalEpochs=state.get("total_epochs", 0),
            currentPhase=current_phase,
            phases=phases,
            status="idle" if not state else "running",
            lastUpdate=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to get training status: {e}")
        return TrainingStatus(status="error", lastUpdate=datetime.now().isoformat())


@router.get("/sync", response_model=SyncStatus)
def get_sync_status():
    """获取 API 同步状态"""
    try:
        log_path = "/var/log/model_sync.log"
        log_content = read_log_file(log_path, lines=20)
        
        # 解析最后同步时间
        last_sync = None
        model_synced = False
        sensor_synced = False
        
        for line in log_content.split('\n'):
            if "Successfully downloaded latest model" in line:
                model_synced = True
            if "Successfully downloaded sensor data" in line:
                sensor_synced = True
            if "同步完成" in line:
                # 解析时间戳 [2026-01-28 01:10:03]
                try:
                    ts = line.split(']')[0].strip('[')
                    last_sync = ts
                except:
                    pass
        
        return SyncStatus(
            modelSynced=model_synced,
            sensorDataSynced=sensor_synced,
            lastSyncTime=last_sync,
            status="ok" if model_synced else "unknown"
        )
    except Exception as e:
        logger.error(f"Failed to get sync status: {e}")
        return SyncStatus(status="error")


@router.get("/logs/{log_type}")
def get_logs(log_type: str, lines: int = 100):
    """
    获取日志内容
    
    log_type: download | training | sync
    """
    # S3 日志路径映射
    s3_log_keys = {
        "download": "logs/download.log",
        "training": "logs/training.log",
    }
    
    # 本地日志路径映射
    local_log_paths = {
        "sync": "/var/log/model_sync.log",
    }
    
    if log_type in s3_log_keys:
        # 从 S3 读取日志
        content = read_s3_log(s3_log_keys[log_type], lines=lines)
        return {
            "type": log_type,
            "source": "s3",
            "path": f"s3://{S3_BUCKET}/{s3_log_keys[log_type]}",
            "lines": content.split('\n') if content else [],
            "timestamp": datetime.now().isoformat()
        }
    elif log_type in local_log_paths:
        # 读取本地日志
        content = read_log_file(local_log_paths[log_type], lines=lines)
        return {
            "type": log_type,
            "source": "local",
            "path": local_log_paths[log_type],
            "lines": content.split('\n') if content else [],
            "timestamp": datetime.now().isoformat()
        }
    else:
        return {
            "type": log_type,
            "message": f"Unknown log type: '{log_type}'. Valid types: download, training, sync",
            "lines": []
        }
