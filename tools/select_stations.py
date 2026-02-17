"""选出 4 个代表基站（东西南北）并计算两两距离"""
import json
import math

COORDS_FILE = "../services/training/station_coords.json"

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))

with open(COORDS_FILE) as f:
    stations = json.load(f)

# 候选 4 站 (数据量充足 + 地理分散)
pick = {
    "N: S66 Kranji":  stations["S66"],   # lat=1.4387, 215 rain samples
    "S: S60 Sentosa": stations["S60"],   # lat=1.2500, 107 rain samples
    "E: S24 Changi":  stations["S24"],   # lon=103.98, 123 rain samples
    "W: S44 Jurong":  stations["S44"],   # lon=103.68, 141 rain samples
}

print("=== Selected 4 Stations ===")
for name, c in pick.items():
    print(f"  {name:20s}  lat={c['lat']:.5f}  lon={c['lon']:.5f}")

print("\n=== Pairwise Distances ===")
names = list(pick.keys())
coords = list(pick.values())
for i in range(len(names)):
    for j in range(i + 1, len(names)):
        d = haversine(
            coords[i]["lat"], coords[i]["lon"],
            coords[j]["lat"], coords[j]["lon"],
        )
        status = "OK" if d > 5 else "TOO CLOSE"
        print(f"  {names[i][:12]:>12} <-> {names[j][:12]:>12}: {d:5.1f} km  {status}")
