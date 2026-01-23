import os
import glob
import numpy as np
import xarray as xr
import torch
import torch.nn.functional as F
# from tqdm import tqdm
from weather_dataset import latlon2xy # Import projection logic

# Config
RAW_DIR = "satellite_data"
PROCESSED_DIR = "processed_data"
TARGET_SIZE = (64, 64)

# Singapore Crop Box (Must match weather_dataset.py)
SG_LAT_MAX, SG_LON_MIN = 1.50, 103.6
C1, L1 = latlon2xy(SG_LAT_MAX, SG_LON_MIN) 
SG_LAT_MIN, SG_LON_MAX = 1.15, 104.1
C2, L2 = latlon2xy(SG_LAT_MIN, SG_LON_MAX)


def preprocess(input_dirs):
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)
        
    all_files = []
    
    print(f"Scanning directories: {input_dirs}")
    
    for d in input_dirs:
        # Check if directory exists
        if not os.path.exists(d):
            print(f"Warning: Directory '{d}' not found. Skipping.")
            continue
            
        found_files = glob.glob(os.path.join(d, "NC_H09_*.nc"))
        print(f"Found {len(found_files)} satellite files in '{d}'.")
        all_files.extend(found_files)
        
    if not all_files:
        print("No files found in any of the specified directories.")
        return

    print(f"Total files to process: {len(all_files)}")
    
    for i, fpath in enumerate(all_files):
        print(f"Processing {i+1}/{len(all_files)}: {os.path.basename(fpath)}")
        fname = os.path.basename(fpath)
        # Check if already done
        out_name = fname.replace(".nc", ".npy")
        out_path = os.path.join(PROCESSED_DIR, out_name)
        
        if os.path.exists(out_path):
            continue
            
        try:
            ds = xr.open_dataset(fpath, decode_timedelta=False)
            
            # Determine variable name
            var_name = 'tbb'
            if 'tbb_13' in ds:
                var_name = 'tbb_13'
                
            if var_name not in ds:
                print(f"Skipping {fname}: Variable not found.")
                continue

            # Check dimensions (Full Disk vs Dummy)
            if ds[var_name].shape[0] > 1000:
                # FULL DISK -> CROP
                # Ensure indices are ordered
                r_min, r_max = min(L1, L2), max(L1, L2)
                c_min, c_max = min(C1, C2), max(C1, C2)
                
                # Extract
                data = ds[var_name][r_min:r_max, c_min:c_max].values
                
                # Resize
                # Input to interpolate must be (Batch, Channel, H, W) -> (1, 1, H, W)
                tensor = torch.tensor(data, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
                resized = F.interpolate(tensor, size=TARGET_SIZE, mode='bilinear', align_corners=False)
                
                # Squeeze back to (64, 64)
                final_arr = resized.squeeze().numpy()
                
            else:
                # DUMMY -> Just load
                data = ds[var_name].values
                # Ensure 64x64
                if data.shape != TARGET_SIZE:
                     tensor = torch.tensor(data, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
                     resized = F.interpolate(tensor, size=TARGET_SIZE, mode='bilinear', align_corners=False)
                     final_arr = resized.squeeze().numpy()
                else:
                     final_arr = data

            # Normalize here? 
            # Better to normalize in Dataset (runtime) or here (storage)?
            # Storing raw Kelvin values (float) is more flexible. 
            # But converting to float16 could save space.
            # Let's keep as float32 raw Kelvin values for consistency with original script.
            
            np.save(out_path, final_arr)
            ds.close()
            
        except Exception as e:
            print(f"Error processing {fname}: {e}")

    print("Preprocessing Complete!")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Preprocess Satellite Data")
    parser.add_argument("--dirs", nargs='+', default=[RAW_DIR], help="List of folders containing satellite .nc files")
    args = parser.parse_args()
    
    preprocess(args.dirs)
