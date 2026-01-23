import numpy as np
import xarray as xr
import pandas as pd
import os
import datetime

# --- Configuration ---
START_DATE = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
NUM_HOURS = 24  # Generate 24 hours of data
# Singapore Region (approx)
# Lat: 1.2 ~ 1.5, Lon: 103.6 ~ 104.1
# Let's make a grid of 64x64 pixels covering a slightly larger area
LATS = np.linspace(1.0, 1.7, 64)
LONS = np.linspace(103.5, 104.2, 64)

DATA_DIR = "satellite_data" # Change to target dir
# Mock 'Sensor' locations (e.g., Changi Airport, Jurong West)
SENSORS = [
    {"id": "S24", "lat": 1.3678, "lon": 103.9826, "name": "Changi"},
    {"id": "S44", "lat": 1.3455, "lon": 103.6806, "name": "Jurong"},
    {"id": "S50", "lat": 1.3337, "lon": 103.7768, "name": "Clementi"},
    {"id": "S109", "lat": 1.3764, "lon": 103.8492, "name": "Ang Mo Kio"},
]

def create_dirs():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    print(f"Created directory: {DATA_DIR}")

def generate_satellite_images():
    print("Generating MOCK JAXA Himawari-9 Full Disk images (NetCDF)...")
    
    # Clean up old files to avoid confusion
    import glob
    old = glob.glob(os.path.join(DATA_DIR, "NC_H09_*.nc"))
    for f in old:
        try: os.remove(f) 
        except: pass
    
    for i in range(NUM_HOURS * 6): # Every 10 mins
        current_time = START_DATE + datetime.timedelta(minutes=i*10)
        
        # 1. Simulate Cloud Cover (random blobs)
        noise = np.random.rand(64, 64)
        cloud_data = (noise + np.roll(noise, 1, axis=0) + np.roll(noise, 1, axis=1)) / 3.0
        
        # Band 13 (Infrared) brightness temperature (Kelvin).
        tbb_data = 300 - (cloud_data * 100) # 200~300 range

        # Create xarray Dataset
        # MOCKING A FULL DISK CROP
        # We pretend this file is a "Full Disk" file but physically it only contains 64x64 pixels
        # However, to pass the "Full Disk" check in weather_dataset.py, we might need to fake dimensions?
        # Actually weather_dataset.py handles small "dummy" files too.
        # But to test the "Real Pipeline" path, we name it like a real file.
        
        ds = xr.Dataset(
            data_vars=dict(
                tbb_13=(["lat", "lon"], tbb_data) # Real data uses tbb_13
            ),
            coords=dict(
                lon=(["lon"], LONS),
                lat=(["lat"], LATS),
                time=current_time
            ),
            attrs=dict(description="Mock JAXA Data for Singapore Testing")
        )
        
        # Filename format: NC_H09_YYYYMMDD_HHMM_R21_FLDK.02401_02401.nc
        # We use a suffix that LOOKS like a real file but clearly marked mock
        fname = f"NC_H09_{current_time.strftime('%Y%m%d_%H%M')}_R21_FLDK.02401_02401.nc"
        fpath = os.path.join(DATA_DIR, fname)
        ds.to_netcdf(fpath)
        
    print(f"Generated {NUM_HOURS * 6} MOCK satellite files in {DATA_DIR}")

def generate_sensor_data():
    print("Generating MOCK ground sensor data (CSV)...")
    
    # Generating 1-minute interval data to test resampling logic
    timestamps = []
    num_steps = NUM_HOURS * 60 # 24 hours * 60 mins
    
    for i in range(num_steps):
        timestamps.append(START_DATE + datetime.timedelta(minutes=i))
        
    all_readings = []
    
    for sensor in SENSORS:
        base_temp = 28.0
        temps = base_temp + np.random.randn(num_steps).cumsum() * 0.05
        # Rain spikes
        rain = np.zeros(num_steps)
        # Random storm event
        start_rain = np.random.randint(0, num_steps-60)
        rain[start_rain:start_rain+30] = np.random.uniform(0.1, 5.0, 30)
        
        df = pd.DataFrame({
            "timestamp": timestamps,
            "sensor_id": sensor["id"],
            "temperature": temps,
            "rainfall": rain,
            "humidity": np.random.uniform(70, 95, size=num_steps)
        })
        all_readings.append(df)
        
    final_df = pd.concat(all_readings)
    # Overwrite the 'real' file to test the pipeline
    csv_path = "real_sensor_data.csv"
    final_df.to_csv(csv_path, index=False)
    print(f"Generated MOCK sensor data: {csv_path}")

if __name__ == "__main__":
    create_dirs()
    generate_satellite_images()
    generate_sensor_data()
    print("\nDone! MOCK dataset generated. You can now run preprocess_images.py and train.py.")
