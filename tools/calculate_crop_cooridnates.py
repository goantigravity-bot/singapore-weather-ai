import numpy as np

# --- Himawari-9 L3 Gridded (EQR) Constants ---
# Based on JAXA P-Tree Specs:
# Projection: Equirectangular (EQR)
# Area: 60N to 60S, 70E to 150W
# Resolution: 0.02 degrees (approx 2km at equator)
# Origin (0,0) is Top-Left: (60N, 70E)

LAT_MAX = 60.0    # Top Latitude
LON_MIN = 70.0    # Left Longitude
RES = 0.02        # Degrees per pixel

def latlon2xy_eqr(lat, lon):
    """
    Convert Lat/Lon to Pixel Coordinates (Row, Col) for JAXA EQR L3 Data.
    y = (Lat_Max - Lat) / Res
    x = (Lon - Lon_Min) / Res
    """
    y = (LAT_MAX - lat) / RES
    x = (lon - LON_MIN) / RES
    return int(round(x)), int(round(y))

# Singapore Crop Box
SG_LAT_MIN, SG_LAT_MAX = 1.15, 1.50
SG_LON_MIN, SG_LON_MAX = 103.6, 104.1

print(f"--- JAXA Himawari-9 L3 EQR Projection Setup ---")
print(f"Origin (Top-Left): {LAT_MAX}N, {LON_MIN}E")
print(f"Resolution: {RES} deg/pixel")
print("-" * 30)

# Calculate Indices
# Top-Left Pixel
c1, l1 = latlon2xy_eqr(SG_LAT_MAX, SG_LON_MIN) 
# Bottom-Right Pixel
c2, l2 = latlon2xy_eqr(SG_LAT_MIN, SG_LON_MAX)

print(f"Singapore Crop Area ({SG_LAT_MIN}-{SG_LAT_MAX}N, {SG_LON_MIN}-{SG_LON_MAX}E):")
print(f"X (Col) Range: {c1} to {c2} (Width: {c2-c1} pixels)")
print(f"Y (Row) Range: {l1} to {l2} (Height: {l2-l1} pixels)")

print("-" * 30)
print(f"Python Slice Code:")
print(f"data = ds['tbb'][{l1}:{l2}, {c1}:{c2}]")