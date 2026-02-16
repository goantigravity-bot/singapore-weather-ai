#!/usr/bin/env python3
"""
batch_scheduler.py
自动批次调度器 - 管理多批次训练流程

功能:
1. 跟踪训练进度
2. 自动计算下一批日期范围
3. 调用训练脚本
4. 支持断点续训
"""

import os
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# 配置
WORK_DIR = Path("/home/ubuntu/weather-ai")
STATE_FILE = WORK_DIR / "batch_state.json"
BATCH_SIZE_DAYS = 3  # 每批次天数
EPOCHS_PER_BATCH = 100  # 每批次训练轮数

# 训练总目标
TRAINING_START_DATE = "2025-10-01"  # 训练数据起始日期
TRAINING_END_DATE = "2026-01-27"    # 训练数据结束日期


def load_state():
    """加载调度状态"""
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {
        "current_batch": 0,
        "last_completed_date": None,
        "total_batches_completed": 0,
        "total_epochs": 0,
        "history": []
    }


def save_state(state):
    """保存调度状态"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def calculate_next_batch(state):
    """计算下一批训练的日期范围"""
    if state["last_completed_date"]:
        # 从上次完成的日期继续
        start = datetime.strptime(state["last_completed_date"], "%Y-%m-%d") + timedelta(days=1)
    else:
        # 第一次训练
        start = datetime.strptime(TRAINING_START_DATE, "%Y-%m-%d")
    
    end = start + timedelta(days=BATCH_SIZE_DAYS - 1)
    
    # 检查是否超过目标结束日期
    target_end = datetime.strptime(TRAINING_END_DATE, "%Y-%m-%d")
    if start > target_end:
        return None, None, "✅ 所有批次已完成"
    
    if end > target_end:
        end = target_end
    
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), None


def run_batch(start_date, end_date, epochs):
    """运行一个批次的训练"""
    print(f"\n{'='*50}")
    print(f"🚀 启动批次训练")
    print(f"   日期范围: {start_date} 至 {end_date}")
    print(f"   训练轮次: {epochs}")
    print(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")
    
    # 调用训练脚本
    script_path = WORK_DIR / "scripts" / "full_training_pipeline.sh"
    
    result = subprocess.run(
        [str(script_path), start_date, end_date, str(epochs)],
        cwd=str(WORK_DIR),
        capture_output=False
    )
    
    return result.returncode == 0


def run_scheduler(max_batches=None, continuous=False):
    """
    运行调度器
    
    Args:
        max_batches: 最大批次数（None 表示运行所有）
        continuous: 是否连续运行直到完成
    """
    state = load_state()
    batches_run = 0
    
    print("\n" + "="*60)
    print("📋 批次调度器")
    print("="*60)
    print(f"训练范围: {TRAINING_START_DATE} 至 {TRAINING_END_DATE}")
    print(f"批次大小: {BATCH_SIZE_DAYS} 天")
    print(f"已完成批次: {state['total_batches_completed']}")
    print(f"累计 Epochs: {state['total_epochs']}")
    if state['last_completed_date']:
        print(f"上次完成日期: {state['last_completed_date']}")
    print("="*60)
    
    while True:
        # 检查是否达到最大批次数
        if max_batches and batches_run >= max_batches:
            print(f"\n✅ 已完成指定的 {max_batches} 个批次")
            break
        
        # 计算下一批
        start_date, end_date, message = calculate_next_batch(state)
        
        if message:
            print(f"\n{message}")
            break
        
        # 运行批次
        batch_num = state['total_batches_completed'] + 1
        print(f"\n📦 批次 {batch_num}: {start_date} ~ {end_date}")
        
        success = run_batch(start_date, end_date, EPOCHS_PER_BATCH)
        
        if success:
            # 更新状态
            state['current_batch'] = batch_num
            state['last_completed_date'] = end_date
            state['total_batches_completed'] += 1
            state['total_epochs'] += EPOCHS_PER_BATCH
            state['history'].append({
                "batch": batch_num,
                "start_date": start_date,
                "end_date": end_date,
                "epochs": EPOCHS_PER_BATCH,
                "completed_at": datetime.now().isoformat()
            })
            save_state(state)
            
            print(f"\n✅ 批次 {batch_num} 完成")
            batches_run += 1
        else:
            print(f"\n❌ 批次 {batch_num} 失败")
            # 不更新状态，下次重试
            break
        
        # 如果不是连续模式，只运行一批
        if not continuous:
            break
    
    # 打印最终状态
    print("\n" + "="*60)
    print("📊 调度器状态")
    print("="*60)
    print(f"本次运行批次: {batches_run}")
    print(f"累计完成批次: {state['total_batches_completed']}")
    print(f"累计 Epochs: {state['total_epochs']}")
    print(f"下一批起始日期: {state['last_completed_date'] or TRAINING_START_DATE}")
    print("="*60)
    
    return state


def show_status():
    """显示当前状态"""
    state = load_state()
    
    print("\n" + "="*60)
    print("📊 训练进度状态")
    print("="*60)
    
    # 计算总批次数
    start = datetime.strptime(TRAINING_START_DATE, "%Y-%m-%d")
    end = datetime.strptime(TRAINING_END_DATE, "%Y-%m-%d")
    total_days = (end - start).days + 1
    total_batches = (total_days + BATCH_SIZE_DAYS - 1) // BATCH_SIZE_DAYS
    
    completed = state['total_batches_completed']
    progress = (completed / total_batches) * 100 if total_batches > 0 else 0
    
    print(f"训练范围: {TRAINING_START_DATE} 至 {TRAINING_END_DATE}")
    print(f"总天数: {total_days} 天")
    print(f"总批次: {total_batches}")
    print(f"已完成批次: {completed}")
    print(f"进度: {progress:.1f}%")
    print(f"累计 Epochs: {state['total_epochs']}")
    
    # 进度条
    bar_width = 40
    filled = int(bar_width * progress / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    print(f"\n[{bar}] {progress:.1f}%")
    
    if state['last_completed_date']:
        print(f"\n上次完成日期: {state['last_completed_date']}")
        next_start, next_end, msg = calculate_next_batch(state)
        if msg:
            print(msg)
        else:
            print(f"下一批: {next_start} ~ {next_end}")
    
    print("="*60)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="批次训练调度器")
    parser.add_argument("--status", action="store_true", help="显示当前状态")
    parser.add_argument("--run", type=int, default=None, help="运行指定数量的批次")
    parser.add_argument("--continuous", action="store_true", help="连续运行直到完成")
    parser.add_argument("--reset", action="store_true", help="重置调度状态")
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.reset:
        if STATE_FILE.exists():
            os.remove(STATE_FILE)
            print("✅ 调度状态已重置")
        else:
            print("ℹ️ 没有状态文件需要重置")
    elif args.continuous:
        run_scheduler(continuous=True)
    elif args.run:
        run_scheduler(max_batches=args.run)
    else:
        # 默认运行一个批次
        run_scheduler(max_batches=1)
