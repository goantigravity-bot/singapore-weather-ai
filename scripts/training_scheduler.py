#!/usr/bin/env python3
"""
training_scheduler.py
训练调度器 - 检查 S3 数据可用性后执行训练

特点:
1. 检查 S3 中是否有指定日期的数据
2. 只有数据就绪才开始处理
3. 自动继续下一批
"""

import os
import json
import subprocess
import boto3
from datetime import datetime, timedelta
from pathlib import Path
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置
WORK_DIR = Path("/home/ubuntu/weather-ai")
STATE_FILE = WORK_DIR / "training_state.json"
S3_BUCKET = "weather-ai-models-de08370c"
SATELLITE_PREFIX = "satellite"
GOVDATA_PREFIX = "govdata"

# 训练配置
BATCH_SIZE_DAYS = 1  # 每次处理 1 天
EPOCHS_PER_BATCH = 100
TRAINING_START_DATE = "2025-10-01"
TRAINING_END_DATE = "2026-01-27"


def load_state():
    """加载训练状态"""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {
        "last_processed_date": None,
        "total_batches_completed": 0,
        "total_epochs": 0,
        "waiting_for_data": False,
        "history": []
    }


def save_state(state):
    """保存训练状态"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def check_data_available(date_str):
    """
    检查指定日期的数据是否在 S3 中就绪
    通过 .complete 标记文件判断
    """
    date_fmt = date_str.replace("-", "")
    complete_key = f"{SATELLITE_PREFIX}/{date_fmt}/.complete"
    
    try:
        s3 = boto3.client('s3')
        s3.head_object(Bucket=S3_BUCKET, Key=complete_key)
        logger.info(f"✅ 数据就绪: {date_str}")
        return True
    except Exception:
        logger.info(f"⏳ 数据未就绪: {date_str}")
        return False


def download_from_s3(date_str):
    """从 S3 下载指定日期的数据到本地"""
    date_fmt = date_str.replace("-", "")
    
    satellite_dir = WORK_DIR / "satellite_data"
    govdata_dir = WORK_DIR / "govdata"
    
    satellite_dir.mkdir(exist_ok=True)
    govdata_dir.mkdir(exist_ok=True)
    
    logger.info(f"📥 下载卫星数据: {date_str}")
    
    # 下载卫星数据
    result = subprocess.run([
        "aws", "s3", "sync",
        f"s3://{S3_BUCKET}/{SATELLITE_PREFIX}/{date_fmt}/",
        str(satellite_dir) + "/",
        "--exclude", ".complete"
    ], capture_output=True)
    
    if result.returncode != 0:
        logger.error(f"卫星数据下载失败: {result.stderr.decode()}")
        return False
    
    # 下载政府数据
    logger.info(f"📥 下载政府数据: {date_str}")
    for api in ["rainfall", "temperature", "humidity", "pm25"]:
        s3_key = f"{GOVDATA_PREFIX}/{api}_{date_str}.json"
        local_file = govdata_dir / f"{api}_{date_str}.json"
        
        subprocess.run([
            "aws", "s3", "cp",
            f"s3://{S3_BUCKET}/{s3_key}",
            str(local_file)
        ], capture_output=True)
    
    return True


def preprocess_data():
    """预处理数据（裁剪新加坡区域）"""
    logger.info("🔧 预处理卫星数据...")
    
    result = subprocess.run(
        ["python", "preprocess_images.py"],
        cwd=str(WORK_DIR),
        capture_output=True
    )
    
    if result.returncode != 0:
        logger.error(f"预处理失败: {result.stderr.decode()}")
        return False
    
    return True


def cleanup_raw_data():
    """清理原始卫星数据（保留预处理数据）"""
    satellite_dir = WORK_DIR / "satellite_data"
    
    for nc_file in satellite_dir.glob("*.nc"):
        nc_file.unlink()
        
    logger.info("🗑️ 已清理原始卫星数据")


def train_model(epochs):
    """运行模型训练"""
    logger.info(f"🧠 开始训练 ({epochs} epochs)...")
    
    result = subprocess.run(
        ["python", "train_rolling_window.py", "--epochs", str(epochs)],
        cwd=str(WORK_DIR),
        capture_output=False
    )
    
    return result.returncode == 0


def sync_model_to_s3():
    """同步模型到 S3"""
    logger.info("☁️ 同步模型到 S3...")
    
    result = subprocess.run(
        ["./sync_model_to_s3.sh"],
        cwd=str(WORK_DIR),
        capture_output=True
    )
    
    return result.returncode == 0


def sync_sensor_data_to_s3():
    """同步传感器数据到 S3，供 API 服务器使用"""
    logger.info("☁️ 同步传感器数据到 S3...")
    
    sensor_file = WORK_DIR / "real_sensor_data.csv"
    if not sensor_file.exists():
        logger.warning("传感器数据文件不存在，跳过同步")
        return True
    
    result = subprocess.run([
        "aws", "s3", "cp",
        str(sensor_file),
        f"s3://{S3_BUCKET}/sensor_data/real_sensor_data.csv"
    ], capture_output=True)
    
    if result.returncode == 0:
        logger.info("✅ 传感器数据已同步到 S3")
    else:
        logger.error(f"传感器数据同步失败: {result.stderr.decode()}")
    
    return result.returncode == 0


def archive_s3_data(date_str):
    """将 S3 中的原始数据移动到归档目录"""
    date_fmt = date_str.replace("-", "")
    
    logger.info(f"📦 归档 S3 数据: {date_str}")
    
    # 移动卫星数据
    subprocess.run([
        "aws", "s3", "mv",
        f"s3://{S3_BUCKET}/{SATELLITE_PREFIX}/{date_fmt}/",
        f"s3://{S3_BUCKET}/archived/{SATELLITE_PREFIX}/{date_fmt}/",
        "--recursive"
    ], capture_output=True)
    
    # 移动政府数据
    for api in ["rainfall", "temperature", "humidity", "pm25"]:
        subprocess.run([
            "aws", "s3", "mv",
            f"s3://{S3_BUCKET}/{GOVDATA_PREFIX}/{api}_{date_str}.json",
            f"s3://{S3_BUCKET}/archived/{GOVDATA_PREFIX}/{api}_{date_str}.json"
        ], capture_output=True)


def send_notification(success, date_str, error_msg=None):
    """发送邮件通知"""
    try:
        if success:
            subprocess.run([
                "python", "-c", f"""
from notification import send_training_success_email
send_training_success_email('', '', {{'date': '{date_str}'}})
"""
            ], cwd=str(WORK_DIR))
        else:
            subprocess.run([
                "python", "-c", f"""
from notification import send_training_failure_email
send_training_failure_email('{error_msg}', 'Batch {date_str}')
"""
            ], cwd=str(WORK_DIR))
    except Exception as e:
        logger.error(f"发送通知失败: {e}")


def get_next_date(state):
    """获取下一个要处理的日期"""
    if state["last_processed_date"]:
        last = datetime.strptime(state["last_processed_date"], "%Y-%m-%d")
        next_date = last + timedelta(days=1)
    else:
        next_date = datetime.strptime(TRAINING_START_DATE, "%Y-%m-%d")
    
    end_date = datetime.strptime(TRAINING_END_DATE, "%Y-%m-%d")
    
    if next_date > end_date:
        return None  # 所有批次已完成
    
    return next_date.strftime("%Y-%m-%d")


def run_scheduler(max_batches=None, wait_for_data=True):
    """
    运行训练调度器
    
    Args:
        max_batches: 最大批次数（None = 无限制）
        wait_for_data: 数据不可用时是否等待
    """
    state = load_state()
    batches_run = 0
    
    logger.info("=" * 60)
    logger.info("🚀 训练调度器启动")
    logger.info(f"已完成批次: {state['total_batches_completed']}")
    logger.info(f"上次处理: {state['last_processed_date'] or '无'}")
    logger.info("=" * 60)
    
    while True:
        # 检查批次限制
        if max_batches and batches_run >= max_batches:
            logger.info(f"✅ 已完成 {max_batches} 个批次")
            break
        
        # 获取下一个日期
        next_date = get_next_date(state)
        
        if next_date is None:
            logger.info("🎉 所有批次已完成！")
            break
        
        logger.info(f"\n📅 检查日期: {next_date}")
        
        # 检查数据是否可用
        if not check_data_available(next_date):
            if wait_for_data:
                logger.info("⏳ 数据未就绪，等待中...")
                state["waiting_for_data"] = True
                save_state(state)
                break  # 退出，等待下次调度
            else:
                logger.info("⏭️ 跳过未就绪的日期")
                continue
        
        state["waiting_for_data"] = False
        
        # 执行处理流程
        try:
            # 1. 下载数据
            if not download_from_s3(next_date):
                raise Exception("下载失败")
            
            # 2. 预处理
            if not preprocess_data():
                raise Exception("预处理失败")
            
            # 3. 清理原始数据
            cleanup_raw_data()
            
            # 4. 训练
            if not train_model(EPOCHS_PER_BATCH):
                raise Exception("训练失败")
            
            # 5. 同步模型
            if not sync_model_to_s3():
                raise Exception("模型同步失败")
            
            # 5.5 同步传感器数据（供 API 服务器使用）
            sync_sensor_data_to_s3()
            
            # 6. 归档 S3 数据
            archive_s3_data(next_date)
            
            # 更新状态
            state["last_processed_date"] = next_date
            state["total_batches_completed"] += 1
            state["total_epochs"] += EPOCHS_PER_BATCH
            state["history"].append({
                "date": next_date,
                "completed_at": datetime.now().isoformat()
            })
            save_state(state)
            
            logger.info(f"✅ 批次完成: {next_date}")
            batches_run += 1
            
            # 发送成功通知（可选，每 N 批发一次）
            if batches_run % 10 == 0:
                send_notification(True, next_date)
                
        except Exception as e:
            logger.error(f"❌ 批次失败: {e}")
            send_notification(False, next_date, str(e))
            break
    
    # 打印最终状态
    logger.info("\n" + "=" * 60)
    logger.info("📊 调度器状态")
    logger.info(f"本次运行: {batches_run} 批次")
    logger.info(f"累计完成: {state['total_batches_completed']} 批次")
    logger.info(f"累计 Epochs: {state['total_epochs']}")
    logger.info("=" * 60)
    
    return state


def show_status():
    """显示当前状态"""
    state = load_state()
    
    print("\n" + "=" * 60)
    print("📊 训练进度")
    print("=" * 60)
    
    # 计算进度
    start = datetime.strptime(TRAINING_START_DATE, "%Y-%m-%d")
    end = datetime.strptime(TRAINING_END_DATE, "%Y-%m-%d")
    total_days = (end - start).days + 1
    
    completed = state['total_batches_completed']
    progress = (completed / total_days) * 100 if total_days > 0 else 0
    
    print(f"训练范围: {TRAINING_START_DATE} ~ {TRAINING_END_DATE}")
    print(f"总天数: {total_days}")
    print(f"已完成: {completed}")
    print(f"进度: {progress:.1f}%")
    
    # 进度条
    bar_width = 40
    filled = int(bar_width * progress / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    print(f"\n[{bar}] {progress:.1f}%")
    
    if state['last_processed_date']:
        print(f"\n上次处理: {state['last_processed_date']}")
        next_date = get_next_date(state)
        if next_date:
            available = check_data_available(next_date)
            status = "✅ 就绪" if available else "⏳ 等待数据"
            print(f"下一批: {next_date} - {status}")
    
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="训练调度器")
    parser.add_argument("--status", action="store_true", help="显示状态")
    parser.add_argument("--run", type=int, default=None, help="运行 N 个批次")
    parser.add_argument("--continuous", action="store_true", help="持续运行")
    parser.add_argument("--no-wait", action="store_true", help="数据不可用时不等待")
    parser.add_argument("--reset", action="store_true", help="重置状态")
    
    args = parser.parse_args()
    
    os.chdir(WORK_DIR)
    
    # 加载环境变量
    env_file = WORK_DIR / ".env.production"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, _, value = line.strip().partition('=')
                    os.environ[key] = value.strip('"').strip("'")
    
    if args.status:
        show_status()
    elif args.reset:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
            print("✅ 状态已重置")
    elif args.continuous:
        while True:
            state = run_scheduler(wait_for_data=not args.no_wait)
            if state.get("waiting_for_data"):
                import time
                logger.info("💤 等待 1 小时后重试...")
                time.sleep(3600)
            else:
                break
    elif args.run:
        run_scheduler(max_batches=args.run, wait_for_data=not args.no_wait)
    else:
        run_scheduler(max_batches=1, wait_for_data=not args.no_wait)
