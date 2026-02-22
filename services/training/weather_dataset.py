import torch
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import numpy as np
import os
import logging
import math
import json
import requests
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# --- 卫星图参数（satellite-3ch: B08/B11/B13, 41×37 裁剪区域）---
# 3ch 数据 shape: (41, 37)，不再做 patch 裁剪，直接用整张图
SAT_HEIGHT = 41
SAT_WIDTH = 37
IMG_SIZE = 41  # 保持兼容：用于坐标归一化
SAT_BANDS = ['B08', 'B11', 'B13']
_STATION_COORD_CACHE = os.path.join(os.path.dirname(__file__), 'station_coords.json')

def _load_station_coords():
    """从缓存或 API 获取基站经纬度，返回 {sensor_id: (lat, lon)}。"""
    if os.path.exists(_STATION_COORD_CACHE):
        with open(_STATION_COORD_CACHE) as f:
            return json.load(f)

    # 首次运行时从 API 拉取并缓存
    try:
        resp = requests.get('https://api.data.gov.sg/v1/environment/rainfall', timeout=10)
        stations = resp.json().get('metadata', {}).get('stations', [])
        coords = {s['id']: {'lat': s['location']['latitude'], 'lon': s['location']['longitude']} for s in stations}
        with open(_STATION_COORD_CACHE, 'w') as f:
            json.dump(coords, f, indent=2)
        logger.info(f"Cached {len(coords)} station coordinates to {_STATION_COORD_CACHE}")
        return coords
    except Exception as e:
        logger.warning(f"Failed to load station coords: {e}, using empty map")
        return {}

def _latlon_to_pixel(lat, lon):
    """基站经纬度 → 128×128 卫星图的像素坐标 (px, py)。"""
    py = int((SG_LAT_MAX - lat) / (SG_LAT_MAX - SG_LAT_MIN) * IMG_SIZE)
    px = int((lon - SG_LON_MIN) / (SG_LON_MAX - SG_LON_MIN) * IMG_SIZE)
    return px, py

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
        
        # 滑动窗口：可通过环境变量限制训练数据时间范围，默认使用全部历史
        MAX_TRAINING_DAYS = int(os.environ.get("MAX_TRAINING_DAYS", "99999"))
        
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
        
        # --- 基站坐标 → 像素映射（局部裁剪用）---
        raw_coords = _load_station_coords()
        self._station_pixel = {}  # {sensor_id: (px, py)}
        for sid, c in raw_coords.items():
            px, py = _latlon_to_pixel(c['lat'], c['lon'])
            self._station_pixel[sid] = (px, py)
        logger.info(f"Station pixel map: {len(self._station_pixel)} stations mapped")

        # --- 预加载 3 通道卫星 .npy (B08/B11/B13) 到内存 ---
        self._sat_cache = {}
        self.available_sat_timestamps = set()

        # 使用传入的 sat_dir 参数加载 3 通道卫星数据，支持按月子目录结构
        if os.path.exists(sat_dir):
            # 递归扫描所有子目录收集 .npy 文件，按时间戳分组
            band_files = {}  # {ts_str: {band: filepath}}
            for root, _, files in os.walk(sat_dir):
                for f in files:
                    if not f.endswith(".npy"):
                        continue
                    for band in SAT_BANDS:
                        prefix = f"SAT_{band}_"
                        if f.startswith(prefix):
                            base = f.replace(".npy", "")
                            parts = base.split("_")
                            if len(parts) >= 4:
                                ts_str = f"{parts[2]}_{parts[3]}"
                                band_files.setdefault(ts_str, {})[band] = os.path.join(root, f)
                            break
            
            # 堆叠三个波段为 (3, H, W)
            for ts_str, bands in band_files.items():
                if len(bands) == len(SAT_BANDS):
                    try:
                        layers = [np.load(bands[b]) for b in SAT_BANDS]
                        self._sat_cache[ts_str] = np.stack(layers, axis=0)  # (3, 41, 37)
                        self.available_sat_timestamps.add(ts_str)
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

        
        # 2. Sensor data is already resampled to 10-min in CSV generation,
        # just ensure wind columns exist for backward compatibility
        import time as _time
        _t0 = _time.time()
        logger.info(f"Phase 2: Aligning {len(self.sensor_df):,} sensor rows with {len(sat_index_df)} sat timestamps...")
        if 'wind_speed' not in self.sensor_df.columns:
            self.sensor_df['wind_speed'] = 0.0
        if 'wind_direction' not in self.sensor_df.columns:
            self.sensor_df['wind_direction'] = 0.0

        full_resampled = self.sensor_df

        # 3. Join with Satellite Availability
        logger.info("Phase 3: pd.merge (left join with sat timestamps)...")
        merged = pd.merge(full_resampled, sat_index_df[['ts_match']], left_on='timestamp', right_on='ts_match', how='left', indicator='has_sat')
        merged['valid_sat'] = (merged['has_sat'] == 'both')
        _t1 = _time.time()
        logger.info(f"  Merge done: {len(merged):,} rows, {_t1-_t0:.1f}s")

        # 4. 向量化 sample 生成
        logger.info("Phase 4: Generating samples...")
        self.samples = []
        self._group_cache = {}
        self._rainfall_cache = {}  # sensor_id → numpy array of rainfall values
        station_count = 0
        
        for sensor_id, group in merged.groupby('sensor_id'):
            num_rows = len(group)
            if num_rows <= self.seq_len:
                continue

            valid_sat_flags = group['valid_sat'].values
            self._group_cache[sensor_id] = group
            self._rainfall_cache[sensor_id] = group['rainfall'].values

            valid_positions = np.where(valid_sat_flags[self.seq_len - 1 : num_rows - self.horizon])[0]
            valid_positions += self.seq_len

            for i in valid_positions:
                self.samples.append((sensor_id, i - self.seq_len, i, i + self.horizon - 1))

            station_count += 1
            if station_count % 10 == 0:
                logger.info(f"  Stations: {station_count}, samples so far: {len(self.samples):,}")

        _t2 = _time.time()
        logger.info(f"✅ Sample generation: {len(self.samples):,} samples, {len(self._group_cache)} stations, {_t2-_t0:.1f}s total")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        sensor_id, input_start, input_end, target_idx = self.samples[idx]
        group = self._group_cache[sensor_id]
        
        # 1. Get Sensor Data (7维: temp, rain, humidity, pm25, wind_speed, wind_dir_sin, wind_dir_cos)
        base_cols = ['temperature', 'rainfall', 'humidity', 'pm25', 'wind_speed', 'wind_direction']
        raw_seq = group.iloc[input_start : input_end][base_cols].values.astype(np.float32)
        
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
        target_val = group.iloc[target_idx]['rainfall']
        target_tensor = torch.tensor([target_val], dtype=torch.float32)
        
        # 3. 从内存缓存获取 3 通道卫星图 (B08/B11/B13)
        current_ts = group.iloc[input_end - 1]['timestamp']
        
        minute = (current_ts.minute // 10) * 10
        sat_ts = current_ts.replace(minute=minute, second=0)
        
        if sat_ts.tzinfo is not None:
             sat_ts_utc = sat_ts.astimezone(timezone.utc)
             utc_str = sat_ts_utc.strftime('%Y%m%d_%H%M')
        else:
             sat_ts_utc = sat_ts - timedelta(hours=8)
             utc_str = sat_ts_utc.strftime('%Y%m%d_%H%M')
        
        data = self._sat_cache.get(utc_str)
        if data is not None:
            # data shape: (3, 41, 37), 温度单位 K
            sat_img = torch.tensor(data, dtype=torch.float32)
            sat_img = (sat_img - 200) / 100.0
        else:
            sat_img = torch.zeros(len(SAT_BANDS), SAT_HEIGHT, SAT_WIDTH)
        
        # 坐标特征 (0~1)
        px, py = self._station_pixel.get(sensor_id, (IMG_SIZE // 2, IMG_SIZE // 2))
        coord_tensor = torch.tensor([px / IMG_SIZE, py / IMG_SIZE], dtype=torch.float32)
        
        return sat_img, sensor_tensor, coord_tensor, target_tensor

def _build_weighted_sampler(subset, rain_threshold=0.1):
    """
    为训练集构建 WeightedRandomSampler，平衡降雨/干燥样本。

    原理：降雨样本被抽中的概率提高到与干燥样本相当，
    使每个 batch 中雨/干比例接近 50:50，而非原始的 2:98。
    """
    from torch.utils.data import WeightedRandomSampler
    import time as _time
    _t0 = _time.time()

    # 直接从 _rainfall_cache numpy 数组读 rainfall，无 pandas 开销
    dataset = subset.dataset
    rain_flags = []
    for idx in subset.indices:
        sensor_id, _, _, target_idx = dataset.samples[idx]
        rainfall = dataset._rainfall_cache[sensor_id][target_idx]
        rain_flags.append(rainfall > rain_threshold)

    n_rain = sum(rain_flags)
    n_dry = len(rain_flags) - n_rain

    _t1 = _time.time()
    if n_rain == 0 or n_dry == 0:
        logger.info(f"⚖️  WeightedSampler skipped (all {'rain' if n_rain else 'dry'}), {_t1-_t0:.1f}s")
        return None

    # 权重 = 1/该类数量，让两类总权重相等
    w_rain = 1.0 / n_rain
    w_dry = 1.0 / n_dry
    weights = [w_rain if is_rain else w_dry for is_rain in rain_flags]

    logger.info(
        f"⚖️  WeightedRandomSampler: {n_rain} rain ({n_rain/len(rain_flags)*100:.1f}%) "
        f"/ {n_dry} dry ({n_dry/len(rain_flags)*100:.1f}%) → balanced, {_t1-_t0:.1f}s"
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
