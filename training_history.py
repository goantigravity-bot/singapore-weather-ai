#!/usr/bin/env python3
"""
训练历史记录工具
记录每次训练的时间、性能指标和配置
"""
import json
import os
from datetime import datetime
from pathlib import Path

HISTORY_FILE = "training_history.json"

def load_history():
    """加载训练历史"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                return json.load(f)
        except:
            return []
    return []

def save_history(history):
    """保存训练历史"""
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def add_training_record(
    start_time,
    end_time,
    duration_seconds,
    metrics,
    data_info,
    training_config,
    success=True,
    error_message=None
):
    """
    添加训练记录
    
    Args:
        start_time: 开始时间（datetime对象）
        end_time: 结束时间（datetime对象）
        duration_seconds: 持续时间（秒）
        metrics: 评估指标字典
        data_info: 数据信息字典
        training_config: 训练配置字典
        success: 是否成功
        error_message: 错误信息（如果失败）
    """
    history = load_history()
    
    record = {
        'id': len(history) + 1,
        'timestamp': start_time.isoformat(),
        'start_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
        'end_time': end_time.strftime('%Y-%m-%d %H:%M:%S'),
        'duration_seconds': duration_seconds,
        'duration_formatted': format_duration(duration_seconds),
        'success': success,
        'metrics': metrics,
        'data_info': data_info,
        'training_config': training_config
    }
    
    if error_message:
        record['error_message'] = error_message
    
    history.append(record)
    save_history(history)
    
    return record

def format_duration(seconds):
    """格式化时长"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}小时{minutes}分{secs}秒"
    elif minutes > 0:
        return f"{minutes}分{secs}秒"
    else:
        return f"{secs}秒"

def get_training_stats():
    """获取训练统计信息"""
    history = load_history()
    
    if not history:
        return None
    
    successful_runs = [r for r in history if r.get('success', False)]
    
    if not successful_runs:
        return {
            'total_runs': len(history),
            'successful_runs': 0,
            'failed_runs': len(history)
        }
    
    # 计算平均时长
    avg_duration = sum(r['duration_seconds'] for r in successful_runs) / len(successful_runs)
    
    # 最快和最慢的训练
    fastest = min(successful_runs, key=lambda x: x['duration_seconds'])
    slowest = max(successful_runs, key=lambda x: x['duration_seconds'])
    
    # 最新的训练
    latest = successful_runs[-1]
    
    # 性能趋势
    mae_values = [r['metrics'].get('mae', 0) for r in successful_runs if 'metrics' in r]
    
    stats = {
        'total_runs': len(history),
        'successful_runs': len(successful_runs),
        'failed_runs': len(history) - len(successful_runs),
        'average_duration': format_duration(avg_duration),
        'average_duration_seconds': avg_duration,
        'fastest_run': {
            'duration': fastest['duration_formatted'],
            'timestamp': fastest['start_time']
        },
        'slowest_run': {
            'duration': slowest['duration_formatted'],
            'timestamp': slowest['start_time']
        },
        'latest_run': {
            'duration': latest['duration_formatted'],
            'timestamp': latest['start_time'],
            'mae': latest['metrics'].get('mae', 0),
            'accuracy': latest['metrics'].get('accuracy', 0)
        }
    }
    
    if mae_values:
        stats['performance'] = {
            'best_mae': min(mae_values),
            'worst_mae': max(mae_values),
            'average_mae': sum(mae_values) / len(mae_values)
        }
    
    return stats

def print_training_history(limit=10):
    """打印训练历史"""
    history = load_history()
    
    if not history:
        print("暂无训练历史记录")
        return
    
    print(f"\n{'='*80}")
    print(f"训练历史记录（最近{min(limit, len(history))}次）")
    print(f"{'='*80}\n")
    
    for record in history[-limit:]:
        status = "✅ 成功" if record.get('success', False) else "❌ 失败"
        print(f"#{record['id']} - {record['start_time']} - {status}")
        print(f"   耗时: {record['duration_formatted']}")
        
        if record.get('success', False) and 'metrics' in record:
            metrics = record['metrics']
            print(f"   MAE: {metrics.get('mae', 0):.4f} mm | "
                  f"RMSE: {metrics.get('rmse', 0):.4f} mm | "
                  f"准确率: {metrics.get('accuracy', 0)*100:.2f}%")
        
        if 'data_info' in record:
            data = record['data_info']
            print(f"   数据: {data.get('sensor_records', 0):,} 条记录")
        
        print()
    
    # 打印统计信息
    stats = get_training_stats()
    if stats:
        print(f"{'='*80}")
        print("统计信息")
        print(f"{'='*80}")
        print(f"总运行次数: {stats['total_runs']}")
        print(f"成功: {stats['successful_runs']} | 失败: {stats['failed_runs']}")
        print(f"平均耗时: {stats['average_duration']}")
        print(f"最快: {stats['fastest_run']['duration']} ({stats['fastest_run']['timestamp']})")
        print(f"最慢: {stats['slowest_run']['duration']} ({stats['slowest_run']['timestamp']})")
        
        if 'performance' in stats:
            perf = stats['performance']
            print(f"\n性能统计:")
            print(f"最佳MAE: {perf['best_mae']:.4f} mm")
            print(f"平均MAE: {perf['average_mae']:.4f} mm")
        
        print(f"{'='*80}\n")

if __name__ == "__main__":
    print_training_history()
