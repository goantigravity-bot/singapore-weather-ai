#!/usr/bin/env python3
"""
将 govdata/*.json 转换为 real_sensor_data.csv
从本地 JSON 文件读取，确保日期与卫星图像对齐
"""
import json
import os
import glob
import pandas as pd
from pathlib import Path

GOVDATA_DIR = Path("govdata")
OUTPUT_FILE = "real_sensor_data.csv"

def parse_json_file(filepath, dtype):
    """解析单个 JSON 文件，处理不同格式"""
    with open(filepath) as f:
        data = json.load(f)
    
    records = []
    items = data.get("items", [])
    
    for item in items:
        timestamp = item.get("timestamp")
        readings = item.get("readings", [])
        
        # PM25 格式不同：readings 是字典而不是列表
        if dtype == "pm25" and isinstance(readings, dict):
            pm25_data = readings.get("pm25_one_hourly", {})
            for region, value in pm25_data.items():
                records.append({
                    "timestamp": timestamp,
                    "station_id": f"PM25_{region}",  # 虚拟 station_id
                    "value": value if value else 0
                })
        elif isinstance(readings, list):
            # 标准格式：rainfall, temperature, humidity
            for reading in readings:
                if isinstance(reading, dict):
                    station_id = reading.get("station_id")
                    value = reading.get("value", 0)
                    records.append({
                        "timestamp": timestamp,
                        "station_id": station_id,
                        "value": value if value else 0
                    })
    
    return records


def main():
    print("🔄 转换 govdata JSON 到 CSV...")
    
    # 查找所有 JSON 文件
    json_files = list(GOVDATA_DIR.glob("*.json"))
    print(f"   找到 {len(json_files)} 个 JSON 文件")
    
    if not json_files:
        print("❌ 没有找到 JSON 文件")
        return
    
    # 按类型分组
    data_by_type = {"rainfall": [], "temperature": [], "humidity": [], "pm25": []}
    
    for f in json_files:
        filename = f.name
        for dtype in data_by_type.keys():
            if filename.startswith(dtype):
                records = parse_json_file(f, dtype)
                for r in records:
                    r["type"] = dtype
                data_by_type[dtype].extend(records)
                print(f"   ✓ {filename}: {len(records)} 条记录")
                break
    
    # 合并数据
    all_data = []
    for dtype, records in data_by_type.items():
        for r in records:
            all_data.append(r)
    
    if not all_data:
        print("❌ 没有数据可转换")
        return
    
    # 创建 DataFrame
    df = pd.DataFrame(all_data)
    
    # 透视表：每个 (timestamp, station_id) 一行，各类型为列
    pivot = df.pivot_table(
        index=["timestamp", "station_id"],
        columns="type",
        values="value",
        aggfunc="first"
    ).reset_index()
    
    # 重命名列
    pivot.columns.name = None
    pivot = pivot.rename(columns={"station_id": "sensor_id"})
    
    # 确保所有列存在
    for col in ["humidity", "pm25", "rainfall", "temperature"]:
        if col not in pivot.columns:
            pivot[col] = 0.0
    
    # 排序列
    pivot = pivot[["timestamp", "sensor_id", "humidity", "pm25", "rainfall", "temperature"]]
    
    # 填充缺失值
    pivot = pivot.fillna(0.0)
    
    # 保存
    pivot.to_csv(OUTPUT_FILE, index=False)
    
    print(f"✅ 已保存到 {OUTPUT_FILE}")
    print(f"   行数: {len(pivot)}")
    print(f"   日期范围: {pivot['timestamp'].min()} ~ {pivot['timestamp'].max()}")

if __name__ == "__main__":
    main()
