import torch
from torch.utils.data import Dataset, DataLoader
import pandas as pd
import xarray as xr
import numpy as np
import os
from datetime import datetime, timezone, timedelta

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
        MAX_TRAINING_DAYS = 30  # 可配置参数
        
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
        
        # --- PRE-SCAN AVAILABLE SATELLITE FILES ---
        self.available_sat_timestamps = set()
        
        processed_dir = "processed_data"
        if os.path.exists(processed_dir):
            npy_files = os.listdir(processed_dir)
            for f in npy_files:
                if f.startswith("NC_H09_") and f.endswith(".npy"):
                    parts = f.split("_")
                    if len(parts) >= 4:
                        ts_str = f"{parts[2]}_{parts[3]}"
                        self.available_sat_timestamps.add(ts_str)

        if os.path.exists(sat_dir):
            raw_files = os.listdir(sat_dir)
            for f in raw_files:
                 if f.startswith("NC_H09_") and f.endswith(".nc"):
                     parts = f.split("_")
                     if len(parts) >= 4:
                        ts_str = f"{parts[2]}_{parts[3]}"
                        self.available_sat_timestamps.add(ts_str)
        
        print(f"Dataset Init: Found {len(self.available_sat_timestamps)} available satellite timestamps.")

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
        for sensor_id, group in self.sensor_df.groupby('sensor_id'):
            group = group.sort_values('timestamp').set_index('timestamp')
            r = group.resample('10min').agg({
                'temperature': 'mean',
                'humidity': 'mean',
                'rainfall': 'sum',
                'pm25': 'mean'
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
        
        # 1. Get Sensor Data
        feature_cols = ['temperature', 'rainfall', 'humidity', 'pm25']
        sensor_seq = group.iloc[sample_info['input_idx_start'] : sample_info['input_idx_end']][feature_cols].values
        
        # NORMALIZATION (Simple Manual Scaling)
        sensor_seq = sensor_seq.astype(np.float32)
        sensor_seq[:, 0] = (sensor_seq[:, 0] - 28.0) / 5.0  # Temp
        sensor_seq[:, 1] = sensor_seq[:, 1] / 10.0          # Rain
        sensor_seq[:, 2] = (sensor_seq[:, 2] - 80.0) / 20.0 # Humidity
        sensor_seq[:, 3] = (sensor_seq[:, 3] - 20.0) / 20.0 # PM2.5 (Mean~10-50?) - Rough norm
        
        sensor_tensor = torch.tensor(sensor_seq, dtype=torch.float32)
        
        # 2. Get Target
        target_val = group.iloc[sample_info['target_idx']]['rainfall']
        target_tensor = torch.tensor([target_val], dtype=torch.float32)
        
        # 3. Get Satellite Image
        current_ts = group.iloc[sample_info['input_idx_end'] - 1]['timestamp']
        
        # Convert timestamps for filename matching
        minute = (current_ts.minute // 10) * 10
        sat_ts = current_ts.replace(minute=minute, second=0)
        
        if sat_ts.tzinfo is not None:
             sat_ts_utc = sat_ts.astimezone(timezone.utc)
             utc_str = sat_ts_utc.strftime('%Y%m%d_%H%M')
        else:
             sat_ts_utc = sat_ts - timedelta(hours=8)
             utc_str = sat_ts_utc.strftime('%Y%m%d_%H%M')
        
        # Try Cache First
        processed_dir = "processed_data"
        npy_path = os.path.join(processed_dir, f"NC_H09_{utc_str}_*.npy")
        npy_files = import_glob().glob(npy_path)
        
        sat_tensor = torch.zeros(1, 64, 64) 
        
        if npy_files:
             try:
                 data = np.load(npy_files[0])
                 sat_tensor = torch.tensor(data, dtype=torch.float32)
                 if sat_tensor.ndim == 2:
                     sat_tensor = sat_tensor.unsqueeze(0)
                 sat_tensor = (sat_tensor - 200) / 100.0
             except: pass
        else:
            # Fallback (Slower raw read)
            pass # In strict mode (which we enforced by algo), we expect file to exist or be cached.
            # But duplicate code for raw reading omitted for brevity as 'preprocess' should handle it.
            # If unmatched, returns zeros (black image).
            pass
        
        return sat_tensor, sensor_tensor, target_tensor

def import_glob():
    import glob
    return glob

def get_dataloaders(csv_path, sat_dir, batch_size=4, split=0.8):
    dataset = WeatherDataset(csv_path, sat_dir)
    train_size = int(split * len(dataset))
    val_size = len(dataset) - train_size
    train_ds, val_ds = torch.utils.data.random_split(dataset, [train_size, val_size])
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
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
