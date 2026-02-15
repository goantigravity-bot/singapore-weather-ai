import torch
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
import os
import logging
import math
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# --- Himawari-9 Constants & Projection Utils (EQR L3) ---
# Projection: Equirectangular (EQR)
# Area: 60N to 60S, 70E to 150W
# Org: Top-Left (60N, 70E)
LAT_MAX = 60.0
LON_MIN = 70.0
RES = 0.02

def latlon2xy(lat, lon):
    """
    Convert Lat/Lon to Pixel Coordinates (Row, Col) for JAXA EQR L3 Data.
    y = (Lat_Max - Lat) / Res
    x = (Lon - Lon_Min) / Res
    """
    y = (LAT_MAX - lat) / RES
    x = (lon - LON_MIN) / RES
    return int(round(x)), int(round(y))
    
# Singapore Crop Box (Approx)
SG_LAT_MIN, SG_LAT_MAX = 1.15, 1.50
SG_LON_MIN, SG_LON_MAX = 103.6, 104.1
# Pre-calculate crop indices
C1, L1 = latlon2xy(SG_LAT_MAX, SG_LON_MIN) # Top-Left (High Lat, Low Lon)
C2, L2 = latlon2xy(SG_LAT_MIN, SG_LON_MAX) # Bottom-Right (Low Lat, High Lon)

class WeatherDataset(Dataset):
    def __init__(self, csv_file, sat_dir, sequence_length=6, prediction_horizon=1):
        """
        Args:
            csv_file (string): Path to the csv file with sensor data.
            sat_dir (string): Directory with all satellite .nc files.
            sequence_length (int): How many past timesteps of sensor data to use.
            prediction_horizon (int): How far ahead to predict.
        """
        self.sensor_df = pd.read_csv(csv_file)
        self.sat_dir = sat_dir
        self.seq_len = sequence_length
        self.horizon = prediction_horizon
        
        self.sensor_df['timestamp'] = pd.to_datetime(self.sensor_df['timestamp'])
        
        # 🆕 滑动窗口优化: 只使用最近N天的数据
        # MAX_TRAINING_DAYS = 30  # 原逻辑：只取最新30天
        MAX_TRAINING_DAYS = 365  # 临时修改：扩大窗口以支持历史数据回放训练 (Oct -> Dec)
        
        if len(self.sensor_df) > 0:
            max_date = self.sensor_df['timestamp'].max()
            cutoff_date = max_date - timedelta(days=MAX_TRAINING_DAYS)
            original_count = len(self.sensor_df)
            
            self.sensor_df = self.sensor_df[self.sensor_df['timestamp'] >= cutoff_date]
            
            print(f"📊 滑动窗口优化:")
            print(f"   - 窗口大小: 最近 {MAX_TRAINING_DAYS} 天")
            print(f"   - 数据范围: {self.sensor_df['timestamp'].min()} 至 {self.sensor_df['timestamp'].max()}")
            print(f"   - 原始记录: {original_count:,} 条")
            print(f"   - 过滤后记录: {len(self.sensor_df):,} 条")
            print(f"   - 减少: {original_count - len(self.sensor_df):,} 条 ({(1 - len(self.sensor_df)/original_count)*100:.1f}%)")
        else:
            print("⚠️  数据集为空")
        
        # --- 一次性预加载所有卫星 .npy 到内存（约 5MB，完全放得下内存）---
        # 避免 __getitem__ 中每次 glob+np.load 磁盘 IO
        self._sat_cache = {}
        self.available_sat_timestamps = set()
        
        processed_dir = "processed_data"
        if os.path.exists(processed_dir):
            for f in os.listdir(processed_dir):
                if (f.startswith("NC_H09_") or f.startswith("NC_H08_")) and f.endswith(".npy"):
                    parts = f.split("_")
                    if len(parts) >= 4:
                        ts_str = f"{parts[2]}_{parts[3]}"
                        self.available_sat_timestamps.add(ts_str)
                        # 预加载到内存
                        try:
                            self._sat_cache[ts_str] = np.load(os.path.join(processed_dir, f))
                        except Exception:
                            pass

        if os.path.exists(sat_dir):
            for f in os.listdir(sat_dir):
                 if (f.startswith("NC_H09_") or f.startswith("NC_H08_")) and f.endswith(".nc"):
                     parts = f.split("_")
                     if len(parts) >= 4:
                        ts_str = f"{parts[2]}_{parts[3]}"
                        self.available_sat_timestamps.add(ts_str)
        
        logger.info(f"Dataset Init: Found {len(self.available_sat_timestamps)} satellite timestamps, {len(self._sat_cache)} preloaded to memory")

        # --- OPTIMIZED TIME ALIGNMENT (Vectorized) ---
        # 1. Create Satellite Index DataFrame
        valid_utc_strs = sorted(list(self.available_sat_timestamps))
        sat_index_df = pd.DataFrame({'utc_str': valid_utc_strs})
        
        # Parse UTC string back to datetime (UTC)
        sat_index_df['ts_utc'] = pd.to_datetime(sat_index_df['utc_str'], format='%Y%m%d_%H%M').dt.tz_localize(timezone.utc)
        
        # Convert to Sensor Timezone (Heuristic: UTC+8 if naive)
        sensor_tz = self.sensor_df['timestamp'].dt.tz
        if sensor_tz:
             sat_index_df['ts_match'] = sat_index_df['ts_utc'].dt.tz_convert(sensor_tz)
        else:
             sat_index_df['ts_match'] = sat_index_df['ts_utc'] + timedelta(hours=8)
             # If sensor is naive, target must be naive
             sat_index_df['ts_match'] = sat_index_df['ts_match'].dt.tz_localize(None)

        
        # 2. Resample Sensor Data (All at once)
        print("Resampling and Aligning data...")
        resampled_dfs = []
        # 确保风数据列存在（旧CSV可能没有，用默认值填充以保持兼容）
        if 'wind_speed' not in self.sensor_df.columns:
            self.sensor_df['wind_speed'] = 0.0
        if 'wind_direction' not in self.sensor_df.columns:
            self.sensor_df['wind_direction'] = 0.0

        for sensor_id, group in self.sensor_df.groupby('sensor_id'):
            group = group.sort_values('timestamp').set_index('timestamp')
            r = group.resample('10min').agg({
                'temperature': 'mean',
                'humidity': 'mean',
                'rainfall': 'sum',
                'pm25': 'mean',
                'wind_speed': 'mean',
                'wind_direction': 'mean'
            }).dropna().reset_index()
            r['sensor_id'] = sensor_id
            resampled_dfs.append(r)
            
        if not resampled_dfs:
            self.samples = []
            return

        full_resampled = pd.concat(resampled_dfs)

        # 3. Join with Satellite Availability
        # Left join to preserve sensor history, flag matches
        merged = pd.merge(full_resampled, sat_index_df[['ts_match']], left_on='timestamp', right_on='ts_match', how='left', indicator='has_sat')
        merged['valid_sat'] = (merged['has_sat'] == 'both')

        # 4. Generate Samples
        self.samples = []
        for sensor_id, group in merged.groupby('sensor_id'):
            # group is sorted because resampled was sorted
            timestamps = group['timestamp'].values
            valid_sat_flags = group['valid_sat'].values
            num_rows = len(group)
            
            if num_rows <= self.seq_len:
                continue

            # Iterate over valid end points
            for i in range(self.seq_len, num_rows - self.horizon + 1):
                # We need Satellite Image at input sequence END (i-1)
                if not valid_sat_flags[i-1]:
                    continue
                
                # Check continuity (optional check for gaps)
                # ...

                self.samples.append({
                    'sensor_id': sensor_id,
                    'input_idx_start': i - self.seq_len,
                    'input_idx_end': i,
                    'target_idx': i + self.horizon - 1,
                    'group_data': group # View into the group dataframe
                })

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        sample_info = self.samples[idx]
        group = sample_info['group_data']
        
        # 1. Get Sensor Data (7维: temp, rain, humidity, pm25, wind_speed, wind_dir_sin, wind_dir_cos)
        base_cols = ['temperature', 'rainfall', 'humidity', 'pm25', 'wind_speed', 'wind_direction']
        raw_seq = group.iloc[sample_info['input_idx_start'] : sample_info['input_idx_end']][base_cols].values.astype(np.float32)
        
        # 风向 sin/cos 编码 — 角度是循环量，0° 和 360° 应等价
        wind_dir_rad = np.radians(raw_seq[:, 5])
        wind_dir_sin = np.sin(wind_dir_rad)
        wind_dir_cos = np.cos(wind_dir_rad)
        
        # 构建 7 维特征: [temp, rain, humidity, pm25, wind_speed, wind_dir_sin, wind_dir_cos]
        sensor_seq = np.column_stack([
            raw_seq[:, :5],   # temp, rain, humidity, pm25, wind_speed
            wind_dir_sin,
            wind_dir_cos
        ])
        
        # NORMALIZATION (Simple Manual Scaling)
        sensor_seq[:, 0] = (sensor_seq[:, 0] - 28.0) / 5.0   # Temp: mean~28°C, std~5°C
        sensor_seq[:, 1] = sensor_seq[:, 1] / 10.0            # Rain: 0~10mm range
        sensor_seq[:, 2] = (sensor_seq[:, 2] - 80.0) / 20.0   # Humidity: mean~80%, std~20%
        sensor_seq[:, 3] = (sensor_seq[:, 3] - 20.0) / 20.0   # PM2.5: mean~20, range 0-60
        sensor_seq[:, 4] = sensor_seq[:, 4] / 10.0            # Wind speed: 0~10 m/s
        # sin/cos 已在 [-1, 1] 范围，无需额外归一化
        
        sensor_tensor = torch.tensor(sensor_seq, dtype=torch.float32)
        
        # 2. Get Target
        target_val = group.iloc[sample_info['target_idx']]['rainfall']
        target_tensor = torch.tensor([target_val], dtype=torch.float32)
        
        # 3. 从内存缓存获取卫星图像（O(1) 哈希查找，零磁盘 IO）
        current_ts = group.iloc[sample_info['input_idx_end'] - 1]['timestamp']
        
        minute = (current_ts.minute // 10) * 10
        sat_ts = current_ts.replace(minute=minute, second=0)
        
        if sat_ts.tzinfo is not None:
             sat_ts_utc = sat_ts.astimezone(timezone.utc)
             utc_str = sat_ts_utc.strftime('%Y%m%d_%H%M')
        else:
             sat_ts_utc = sat_ts - timedelta(hours=8)
             utc_str = sat_ts_utc.strftime('%Y%m%d_%H%M')
        
        # 直接从内存字典取，O(1) 哈希查找
        data = self._sat_cache.get(utc_str)
        if data is not None:
            sat_tensor = torch.tensor(data, dtype=torch.float32)
            if sat_tensor.ndim == 2:
                sat_tensor = sat_tensor.unsqueeze(0)
            sat_tensor = (sat_tensor - 200) / 100.0
        else:
            sat_tensor = torch.zeros(1, 64, 64)
        
        return sat_tensor, sensor_tensor, target_tensor

def _build_weighted_sampler(subset, rain_threshold=0.1):
    """
    为训练集构建 WeightedRandomSampler，平衡降雨/干燥样本。

    原理：降雨样本被抽中的概率提高到与干燥样本相当，
    使每个 batch 中雨/干比例接近 50:50，而非原始的 2:98。
    """
    from torch.utils.data import WeightedRandomSampler

    # 遍历 subset 拿到每个样本的 target（降雨量）
    rain_flags = []
    dataset = subset.dataset
    for idx in subset.indices:
        _, _, target = dataset[idx]
        rain_flags.append(target.item() > rain_threshold)

    n_rain = sum(rain_flags)
    n_dry = len(rain_flags) - n_rain

    if n_rain == 0 or n_dry == 0:
        # 全雨或全干，无法平衡，回退到普通 shuffle
        return None

    # 权重 = 1/该类数量，让两类总权重相等
    w_rain = 1.0 / n_rain
    w_dry = 1.0 / n_dry
    weights = [w_rain if is_rain else w_dry for is_rain in rain_flags]

    logger.info(
        f"⚖️  WeightedRandomSampler: {n_rain} rain ({n_rain/len(rain_flags)*100:.1f}%) "
        f"/ {n_dry} dry ({n_dry/len(rain_flags)*100:.1f}%) → balanced batches"
    )

    return WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)


def get_dataloaders(csv_path, sat_dir, batch_size=4, split=0.8):
    dataset = WeatherDataset(csv_path, sat_dir)

    # 空数据集防护：避免 DataLoader 因 num_samples=0 崩溃
    if len(dataset) == 0:
        raise ValueError(
            f"Dataset is empty (0 samples). "
            f"Check satellite data in processed_data/ and {sat_dir}/"
        )

    train_size = int(split * len(dataset))
    val_size = len(dataset) - train_size

    # 防止 train_size 为 0（数据量极少时）
    if train_size == 0:
        train_size = 1
        val_size = len(dataset) - 1

    train_ds, val_ds = torch.utils.data.random_split(dataset, [train_size, val_size])

    # 加权采样：平衡降雨/干燥样本在每个 batch 中的比例
    sampler = _build_weighted_sampler(train_ds)

    # 多线程数据预取：4 个子进程并行准备下一批数据
    # pin_memory 加速 CPU→GPU 传输，persistent_workers 避免每 epoch 重建进程
    use_workers = 4 if batch_size > 1 else 0
    train_loader = DataLoader(
        train_ds, batch_size=batch_size,
        sampler=sampler,             # sampler 和 shuffle 互斥
        shuffle=(sampler is None),   # 仅 sampler 不可用时 fallback
        num_workers=use_workers, pin_memory=True,
        persistent_workers=(use_workers > 0)
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False,
        num_workers=use_workers, pin_memory=True,
        persistent_workers=(use_workers > 0)
    )
    return train_loader, val_loader

if __name__ == "__main__":
    # Test Logic
    print("--- Testing WeatherDataset ---")
    
    csv_path = "real_sensor_data.csv"
    sat_dir = "satellite_data" # Just a placeholder, checking processed_data mainly
    
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        exit(1)
        
    # 1. Init Dataset
    ds = WeatherDataset(csv_path, sat_dir, sequence_length=6, prediction_horizon=1)
    print(f"Dataset Length: {len(ds)}")
    
    if len(ds) > 0:
        # 2. Check Item
        print("\nChecking first sample:")
        sat, sensor, target = ds[0]
        print(f"Sat Tensor: {sat.shape}, Type: {sat.dtype}, Range: [{sat.min():.2f}, {sat.max():.2f}]")
        print(f"Sensor Tensor: {sensor.shape}, Type: {sensor.dtype}")
        print(f"Target Tensor: {target.shape}, Type: {target.dtype}, Val: {target.item():.4f}")
        
        # 3. Check DataLoader
        print("\nChecking DataLoader batch:")
        loader = DataLoader(ds, batch_size=4, shuffle=True)
        for batch_act in loader:
            b_sat, b_sensor, b_target = batch_act
            print(f"Batch Sat: {b_sat.shape}")
            print(f"Batch Sensor: {b_sensor.shape}")
            print(f"Batch Target: {b_target.shape}")
            break
    else:
        print("Dataset is empty! Check time alignment or file availability.")
