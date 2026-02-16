#!/usr/bin/env python3
"""
训练进度监控脚本
实时显示训练状态
"""
import os
import time
import subprocess

def check_training_status():
    """检查训练状态"""
    print("🔍 检查训练进程...")
    
    # 检查进程
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True
    )
    
    train_processes = [line for line in result.stdout.split('\n') if 'train.py' in line and 'grep' not in line]
    
    if train_processes:
        print("✅ 训练进程正在运行")
        for proc in train_processes:
            parts = proc.split()
            cpu = parts[2]
            mem = parts[3]
            time_running = parts[9]
            print(f"   CPU: {cpu}% | 内存: {mem}% | 运行时间: {time_running}")
    else:
        print("❌ 训练进程未运行")
        return False
    
    # 检查模型文件
    print("\n📁 检查文件...")
    
    if os.path.exists("weather_fusion_model.pth"):
        size = os.path.getsize("weather_fusion_model.pth")
        mtime = os.path.getmtime("weather_fusion_model.pth")
        age = time.time() - mtime
        print(f"   模型文件: {size/1024:.1f} KB (更新于 {age/60:.1f} 分钟前)")
    else:
        print("   ⚠️  模型文件尚未生成")
    
    # 检查数据集大小
    if os.path.exists("real_sensor_data.csv"):
        import pandas as pd
        df = pd.read_csv("real_sensor_data.csv")
        print(f"   传感器数据: {len(df):,} 条记录")
    
    # 检查卫星数据
    if os.path.exists("processed_images"):
        npy_files = [f for f in os.listdir("processed_images") if f.endswith('.npy')]
        print(f"   预处理图像: {len(npy_files)} 个文件")
    
    print("\n💡 提示:")
    print("   - 训练30个epochs可能需要30-60分钟")
    print("   - 可以在另一个终端运行: watch -n 5 'ls -lh weather_fusion_model.pth'")
    print("   - 模型文件大小约270KB，如果文件在更新说明训练正常")
    
    return True

if __name__ == "__main__":
    check_training_status()
