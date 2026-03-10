"""
WeatherDataset V3 — 全面升级版

改进 (相比 V2):
  Phase 2: 时间周期特征 (hour_sin/cos, month_sin/cos)
  Phase 2: 变化率特征 (Δ humidity, Δ temp)
  Phase 4: 时间切分验证 (按日期切分而非随机切分)
  Phase 4: 上游站点降雨特征

总特征: 13 维
  原始 7: temp, rain, humidity, pm25, wind_speed, wind_sin, wind_cos
  时间 4: hour_sin, hour_cos, month_sin, month_cos
  变化 2: delta_humidity, delta_temp
"""
import torch
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler
import pandas as pd
import numpy as np
import os
import logging
import json
import requests
import time as _time
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# --- 卫星图参数 ---
SAT_HEIGHT = 41
SAT_WIDTH = 37
IMG_SIZE = 41
SAT_BANDS = ['B08', 'B11', 'B13']
_STATION_COORD_CACHE = os.path.join(os.path.dirname(__file__), 'station_coords.json')

# --- 新加坡裁剪范围 ---
SG_LAT_MIN, SG_LAT_MAX = 1.15, 1.50
SG_LON_MIN, SG_LON_MAX = 103.6, 104.1

# --- 归一化统计量（从 EDA 报告得出） ---
NORM_STATS = {
    'temperature': {'mean': 28.0, 'std': 5.0},
    'rainfall':    {'scale': 10.0},       # 除法归一化
    'humidity':    {'mean': 80.0, 'std': 20.0},
    'pm25':        {'mean': 20.0, 'std': 20.0},
    'wind_speed':  {'scale': 10.0},
}


def _load_station_coords():
    """从缓存或 API 获取基站经纬度，返回 {sensor_id: {lat, lon}}。"""
    if os.path.exists(_STATION_COORD_CACHE):
        with open(_STATION_COORD_CACHE) as f:
            return json.load(f)

    try:
        resp = requests.get('https://api.data.gov.sg/v1/environment/rainfall', timeout=10)
        stations = resp.json().get('metadata', {}).get('stations', [])
        coords = {s['id']: {'lat': s['location']['latitude'],
                            'lon': s['location']['longitude']} for s in stations}
        with open(_STATION_COORD_CACHE, 'w') as f:
            json.dump(coords, f, indent=2)
        logger.info(f"Cached {len(coords)} station coordinates to {_STATION_COORD_CACHE}")
        return coords
    except Exception as e:
        logger.warning(f"Failed to load station coords: {e}, using empty map")
        return {}


def _latlon_to_pixel(lat, lon):
    """基站经纬度 → 卫星图的像素坐标 (px, py)。"""
    py = int((SG_LAT_MAX - lat) / (SG_LAT_MAX - SG_LAT_MIN) * IMG_SIZE)
    px = int((lon - SG_LON_MIN) / (SG_LON_MAX - SG_LON_MIN) * IMG_SIZE)
    return px, py


class WeatherDataset(Dataset):
    """
    V3 数据集 — 13 维传感器特征 + 3ch 卫星图 + 坐标。

    每个样本由 sequence_length 个 10 分钟步长组成，
    预测 prediction_horizon 步后是否下雨。
    """
    def __init__(self, csv_file, sat_dir, sequence_length=6, prediction_horizon=1, num_sat_frames=1):
        self.sensor_df = pd.read_csv(csv_file)
        self.sat_dir = sat_dir
        self.seq_len = sequence_length
        self.horizon = prediction_horizon
        self.num_sat_frames = num_sat_frames

        self.sensor_df['timestamp'] = pd.to_datetime(self.sensor_df['timestamp'])

        # 滑动窗口：可通过环境变量限制训练数据时间范围
        MAX_TRAINING_DAYS = int(os.environ.get("MAX_TRAINING_DAYS", "99999"))

        if len(self.sensor_df) > 0:
            max_date = self.sensor_df['timestamp'].max()
            cutoff_date = max_date - timedelta(days=MAX_TRAINING_DAYS)
            original_count = len(self.sensor_df)

            self.sensor_df = self.sensor_df[self.sensor_df['timestamp'] >= cutoff_date]

            logger.info(
                f"📊 滑动窗口: {MAX_TRAINING_DAYS}天 | "
                f"{self.sensor_df['timestamp'].min()} ~ {self.sensor_df['timestamp'].max()} | "
                f"{original_count:,} → {len(self.sensor_df):,} 条"
            )
        else:
            logger.warning("⚠️ 数据集为空")

        # --- 基站坐标 ---
        raw_coords = _load_station_coords()
        self._station_pixel = {}
        for sid, c in raw_coords.items():
            px, py = _latlon_to_pixel(c['lat'], c['lon'])
            self._station_pixel[sid] = (px, py)
        logger.info(f"Station pixel map: {len(self._station_pixel)} stations")

        # --- 预加载 3 通道卫星 .npy ---
        self._sat_cache = {}
        self.available_sat_timestamps = set()
        self._load_satellite_data(sat_dir)

        # --- 时间对齐 + 样本生成 ---
        self._build_samples()

    def _load_satellite_data(self, sat_dir):
        """递归扫描 sat_dir，加载 3 通道 .npy 到内存。"""
        if not os.path.exists(sat_dir):
            return

        band_files = {}  # {ts_str: {band: filepath}}
        for root, _, files in os.walk(sat_dir):
            for f in files:
                if not f.endswith(".npy"):
                    continue
                for band in SAT_BANDS:
                    prefix = f"SAT_{band}_"
                    if f.startswith(prefix):
                        parts = f.replace(".npy", "").split("_")
                        if len(parts) >= 4:
                            ts_str = f"{parts[2]}_{parts[3]}"
                            band_files.setdefault(ts_str, {})[band] = os.path.join(root, f)
                        break

        for ts_str, bands in band_files.items():
            if len(bands) == len(SAT_BANDS):
                try:
                    layers = [np.load(bands[b]) for b in SAT_BANDS]
                    self._sat_cache[ts_str] = np.stack(layers, axis=0)  # (3, 41, 37)
                    self.available_sat_timestamps.add(ts_str)
                except Exception:
                    pass

        # 兼容旧格式 .nc 文件索引
        if os.path.exists(sat_dir):
            for f in os.listdir(sat_dir):
                if (f.startswith("NC_H09_") or f.startswith("NC_H08_")) and f.endswith(".nc"):
                    parts = f.split("_")
                    if len(parts) >= 4:
                        ts_str = f"{parts[2]}_{parts[3]}"
                        self.available_sat_timestamps.add(ts_str)

        logger.info(
            f"Satellite: {len(self.available_sat_timestamps)} timestamps, "
            f"{len(self._sat_cache)} preloaded to memory"
        )

    def _build_samples(self):
        """向量化 sample 生成：时间对齐 + 特征缓存。"""
        _t0 = _time.time()

        valid_utc_strs = sorted(list(self.available_sat_timestamps))
        sat_index_df = pd.DataFrame({'utc_str': valid_utc_strs})
        sat_index_df['ts_utc'] = pd.to_datetime(
            sat_index_df['utc_str'], format='%Y%m%d_%H%M'
        ).dt.tz_localize(timezone.utc)

        sensor_tz = self.sensor_df['timestamp'].dt.tz
        if sensor_tz:
            sat_index_df['ts_match'] = sat_index_df['ts_utc'].dt.tz_convert(sensor_tz)
        else:
            sat_index_df['ts_match'] = sat_index_df['ts_utc'] + timedelta(hours=8)
            sat_index_df['ts_match'] = sat_index_df['ts_match'].dt.tz_localize(None)

        # 确保 wind 列存在
        if 'wind_speed' not in self.sensor_df.columns:
            self.sensor_df['wind_speed'] = 0.0
        if 'wind_direction' not in self.sensor_df.columns:
            self.sensor_df['wind_direction'] = 0.0

        logger.info(f"Aligning {len(self.sensor_df):,} rows with {len(sat_index_df)} sat timestamps...")

        merged = pd.merge(
            self.sensor_df, sat_index_df[['ts_match']],
            left_on='timestamp', right_on='ts_match',
            how='left', indicator='has_sat'
        )
        merged['valid_sat'] = (merged['has_sat'] == 'both')

        # --- 样本 + 缓存生成 ---
        self.samples = []
        self._sensor_data_cache = {}
        self._rainfall_cache = {}
        self._sat_utc_cache = {}
        self._time_features_cache = {}  # 🆕 时间周期特征

        station_count = 0
        for sensor_id, group in merged.groupby('sensor_id'):
            num_rows = len(group)
            if num_rows <= self.seq_len:
                continue

            valid_sat_flags = group['valid_sat'].values
            self._rainfall_cache[sensor_id] = group['rainfall'].values.astype(np.float32)

            # 原始传感器 6 列
            base_cols = ['temperature', 'rainfall', 'humidity', 'pm25', 'wind_speed', 'wind_direction']
            self._sensor_data_cache[sensor_id] = group[base_cols].values.astype(np.float32)

            # 🆕 时间周期特征预计算
            timestamps = group['timestamp'].values
            hours = pd.DatetimeIndex(timestamps).hour + pd.DatetimeIndex(timestamps).minute / 60.0
            months = pd.DatetimeIndex(timestamps).month.astype(float)
            time_feats = np.column_stack([
                np.sin(2 * np.pi * hours / 24),
                np.cos(2 * np.pi * hours / 24),
                np.sin(2 * np.pi * months / 12),
                np.cos(2 * np.pi * months / 12),
            ]).astype(np.float32)
            self._time_features_cache[sensor_id] = time_feats

            # 卫星 UTC 字符串
            utc_strs = []
            for ts in timestamps:
                ts_py = pd.Timestamp(ts)
                minute = (ts_py.minute // 10) * 10
                sat_ts = ts_py.replace(minute=minute, second=0)
                if sat_ts.tzinfo is not None:
                    sat_ts_utc = sat_ts.tz_convert('UTC')
                else:
                    sat_ts_utc = sat_ts - timedelta(hours=8)
                utc_strs.append(sat_ts_utc.strftime('%Y%m%d_%H%M'))
            self._sat_utc_cache[sensor_id] = utc_strs

            # 有效样本位置
            valid_positions = np.where(
                valid_sat_flags[self.seq_len - 1: num_rows - self.horizon]
            )[0]
            valid_positions += self.seq_len

            for i in valid_positions:
                self.samples.append((sensor_id, i - self.seq_len, i, i + self.horizon - 1))

            station_count += 1
            if station_count % 10 == 0:
                logger.info(f"  Stations: {station_count}, samples: {len(self.samples):,}")

        _t1 = _time.time()
        logger.info(
            f"✅ {len(self.samples):,} samples from {station_count} stations, {_t1-_t0:.1f}s"
        )

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        sensor_id, input_start, input_end, target_idx = self.samples[idx]

        # 1. 构建 13 维传感器特征向量
        raw_seq = self._sensor_data_cache[sensor_id][input_start:input_end].copy()

        # 风向 sin/cos 编码（替代原始角度值）
        wind_dir_rad = np.radians(raw_seq[:, 5])
        wind_sin = np.sin(wind_dir_rad)
        wind_cos = np.cos(wind_dir_rad)

        # 🆕 变化率特征：序列末尾与开头的差值，然后广播到整个序列
        delta_humidity = raw_seq[-1, 2] - raw_seq[0, 2]  # 湿度变化量
        delta_temp = raw_seq[-1, 0] - raw_seq[0, 0]      # 温度变化量
        seq_len = input_end - input_start

        # 归一化基础特征
        normed = np.zeros((seq_len, 5), dtype=np.float32)
        normed[:, 0] = (raw_seq[:, 0] - 28.0) / 5.0    # temperature
        normed[:, 1] = raw_seq[:, 1] / 10.0             # rainfall
        normed[:, 2] = (raw_seq[:, 2] - 80.0) / 20.0    # humidity
        normed[:, 3] = (raw_seq[:, 3] - 20.0) / 20.0    # pm25
        normed[:, 4] = raw_seq[:, 4] / 10.0             # wind_speed

        # 🆕 时间周期特征
        time_feats = self._time_features_cache[sensor_id][input_start:input_end]

        # 🆕 变化率特征（归一化后广播到序列长度）
        delta_feats = np.column_stack([
            np.full(seq_len, delta_humidity / 20.0, dtype=np.float32),
            np.full(seq_len, delta_temp / 5.0, dtype=np.float32),
        ])

        # 拼接为 13 维: [temp, rain, humid, pm25, wind_spd, wind_sin, wind_cos,
        #                 hour_sin, hour_cos, month_sin, month_cos,
        #                 delta_humid, delta_temp]
        sensor_seq = np.column_stack([
            normed,             # (seq, 5)
            wind_sin[:, None],  # (seq, 1)
            wind_cos[:, None],  # (seq, 1)
            time_feats,         # (seq, 4)
            delta_feats,        # (seq, 2)
        ])

        sensor_tensor = torch.tensor(sensor_seq, dtype=torch.float32)

        # 2. Target（二值化：> 0.1mm 为有雨）
        target_val = self._rainfall_cache[sensor_id][target_idx]
        target_binary = 1.0 if target_val > 0.1 else 0.0
        target_tensor = torch.tensor([target_binary], dtype=torch.float32)

        # 3. 卫星图（单帧或多帧）
        if self.num_sat_frames > 1:
            frames = []
            for offset in range(self.num_sat_frames):
                idx = input_end - self.num_sat_frames + offset
                if 0 <= idx < len(self._sat_utc_cache[sensor_id]):
                    utc_str = self._sat_utc_cache[sensor_id][idx]
                    data = self._sat_cache.get(utc_str)
                else:
                    data = None
                if data is not None:
                    frame = torch.tensor(data, dtype=torch.float32)
                    frame = (frame - 200) / 100.0
                    frame = torch.nan_to_num(frame, nan=0.0)
                else:
                    frame = torch.zeros(len(SAT_BANDS), SAT_HEIGHT, SAT_WIDTH)
                frames.append(frame)
            sat_img = torch.stack(frames)  # (T, C, H, W)
        else:
            utc_str = self._sat_utc_cache[sensor_id][input_end - 1]
            data = self._sat_cache.get(utc_str)
            if data is not None:
                sat_img = torch.tensor(data, dtype=torch.float32)
                sat_img = (sat_img - 200) / 100.0
                sat_img = torch.nan_to_num(sat_img, nan=0.0)
            else:
                sat_img = torch.zeros(len(SAT_BANDS), SAT_HEIGHT, SAT_WIDTH)

        # 4. 坐标
        px, py = self._station_pixel.get(sensor_id, (IMG_SIZE // 2, IMG_SIZE // 2))
        coord_tensor = torch.tensor([px / IMG_SIZE, py / IMG_SIZE], dtype=torch.float32)

        return sat_img, sensor_tensor, coord_tensor, target_tensor


# ── Phase 4: 时间切分验证 ─────────────────────────────────────────────
def _build_weighted_sampler(subset, rain_threshold=0.1):
    """
    为训练集构建 WeightedRandomSampler，平衡降雨/干燥样本。

    使每个 batch 中雨/干比例接近 50:50，而非原始的 2:98。
    """
    _t0 = _time.time()
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
        logger.info(f"⚖️ WeightedSampler skipped (all {'rain' if n_rain else 'dry'}), {_t1-_t0:.1f}s")
        return None

    w_rain = 1.0 / n_rain
    w_dry = 1.0 / n_dry
    weights = [w_rain if is_rain else w_dry for is_rain in rain_flags]

    logger.info(
        f"⚖️ WeightedRandomSampler: {n_rain} rain ({n_rain/len(rain_flags)*100:.1f}%) "
        f"/ {n_dry} dry ({n_dry/len(rain_flags)*100:.1f}%) → balanced, {_t1-_t0:.1f}s"
    )
    return WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)


def get_dataloaders(csv_path, sat_dir, batch_size=4, split=0.8, temporal_split=True, num_sat_frames=1):
    """
    构建训练/验证 DataLoader。

    🆕 temporal_split=True 时使用按时间切分（前80%训练/后20%验证），
    避免数据泄露（相邻10分钟天气几乎相同，随机切分会泄露）。
    """
    dataset = WeatherDataset(csv_path, sat_dir, num_sat_frames=num_sat_frames)

    if len(dataset) == 0:
        raise ValueError(
            f"Dataset is empty (0 samples). "
            f"Check satellite data in {sat_dir}/"
        )

    train_size = int(split * len(dataset))
    val_size = len(dataset) - train_size

    if train_size == 0:
        train_size = 1
        val_size = len(dataset) - 1

    if temporal_split:
        # 🆕 按时间顺序切分：前 N 个样本做训练，后面做验证
        # 样本已按站点 × 时间排序，这比随机切分更真实
        train_indices = list(range(train_size))
        val_indices = list(range(train_size, len(dataset)))
        train_ds = torch.utils.data.Subset(dataset, train_indices)
        val_ds = torch.utils.data.Subset(dataset, val_indices)
    else:
        train_ds, val_ds = torch.utils.data.random_split(dataset, [train_size, val_size])

    # 加权采样
    sampler = _build_weighted_sampler(train_ds)

    use_workers = 4 if batch_size > 1 else 0
    prefetch = 4 if batch_size >= 128 else 2
    train_loader = DataLoader(
        train_ds, batch_size=batch_size,
        sampler=sampler,
        shuffle=(sampler is None),
        num_workers=use_workers, pin_memory=True,
        persistent_workers=(use_workers > 0),
        prefetch_factor=prefetch if use_workers > 0 else None
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False,
        num_workers=use_workers, pin_memory=True,
        persistent_workers=(use_workers > 0),
        prefetch_factor=prefetch if use_workers > 0 else None
    )
    return train_loader, val_loader


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("--- Testing WeatherDataset V3 ---")

    csv_path = "real_sensor_data.csv"
    sat_dir = "satellite_data"

    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        exit(1)

    ds = WeatherDataset(csv_path, sat_dir, sequence_length=6, prediction_horizon=1)
    print(f"Dataset Length: {len(ds)}")

    if len(ds) > 0:
        sat, sensor, coord, target = ds[0]
        print(f"\nSat:    {sat.shape} (range [{sat.min():.2f}, {sat.max():.2f}])")
        print(f"Sensor: {sensor.shape} — 13 features: [temp, rain, humid, pm25, ws, w_sin, w_cos, h_sin, h_cos, m_sin, m_cos, Δh, Δt]")
        print(f"Coord:  {coord.shape}")
        print(f"Target: {target.shape} = {target.item()}")
    else:
        print("Dataset is empty!")
