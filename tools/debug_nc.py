import xarray as xr
import glob
import os

# Singapore Region
SG_LAT_MIN, SG_LAT_MAX = 1.15, 1.50
SG_LON_MIN, SG_LON_MAX = 103.6, 104.1

def check_coverage(fpath):
    try:
        ds = xr.open_dataset(fpath, decode_timedelta=False)
        attrs = ds.attrs
        
        lat_ul = float(attrs.get('upper_left_latitude', -999))
        lon_ul = float(attrs.get('upper_left_longitude', -999))
        res = float(attrs.get('grid_interval', 0.02))
        lines = int(attrs.get('line_number', 0))
        pixels = int(attrs.get('pixel_number', 0))
        
        lat_min = lat_ul - (lines * res)
        # lat_max is lat_ul
        
        lon_max = lon_ul + (pixels * res)
        # lon_min is lon_ul
        
        # Check Singapore (1.3N, 103.8E)
        covers_lat = (lat_ul >= SG_LAT_MAX) and (lat_min <= SG_LAT_MIN)
        covers_lon = (lon_ul <= SG_LON_MIN) and (lon_max >= SG_LON_MAX)
        
        ds.close()
        
        if covers_lat and covers_lon:
            return True, f"Valid (Lat:{lat_min:.1f}~{lat_ul:.1f}, Lon:{lon_ul:.1f}~{lon_max:.1f})"
        else:
            return False, f"INVALID REGION (Lat:{lat_min:.1f}~{lat_ul:.1f}, Lon:{lon_ul:.1f}~{lon_max:.1f})"
            
    except Exception as e:
        return False, f"Error: {e}"

files = glob.glob("satellite_data/NC_H09_*.nc")
print(f"Scanning {len(files)} files...\n")

valid_count = 0
for f in files:
    is_valid, msg = check_coverage(f)
    fname = os.path.basename(f)
    if is_valid:
        print(f"✅ {fname}")
        valid_count += 1
    else:
        print(f"❌ {fname} -> {msg}")

print(f"\nSummary: {valid_count}/{len(files)} files are valid for Singapore.")
