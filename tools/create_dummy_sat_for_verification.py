
import os
import numpy as np
from datetime import datetime, timedelta, timezone

def generate_dummy_data():
    processed_dir = "processed_data"
    os.makedirs(processed_dir, exist_ok=True)
    
    # Generate for last 3 days to cover "2 days ago" to "now"
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=3)
    
    curr = start_date
    count = 0
    print(f"Generating dummy data from {start_date} to {end_date}...")
    
    while curr < end_date:
        # Every 10 mins
        minute = (curr.minute // 10) * 10
        ts = curr.replace(minute=minute, second=0, microsecond=0)
        
        # Filename format: NC_H09_YYYYMMDD_HHMM_... .npy
        date_str = ts.strftime("%Y%m%d")
        time_str = ts.strftime("%H%M")
        
        fname = f"NC_H09_{date_str}_{time_str}_dummy.npy"
        fpath = os.path.join(processed_dir, fname)
        
        if not os.path.exists(fpath):
            # Create random 64x64
            data = np.random.rand(64, 64).astype(np.float32)
            np.save(fpath, data)
            count += 1
            
        curr += timedelta(minutes=10)
        
    print(f"Generated {count} dummy files in {processed_dir}")

if __name__ == "__main__":
    generate_dummy_data()
