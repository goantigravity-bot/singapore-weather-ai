import requests
import numpy as np
import json
from scipy.spatial.distance import cdist

def fetch_osm_path(query):
    print(f"Querying Overpass API for: {query}")
    overpass_url = "http://overpass-api.de/api/interpreter"
    
    # Singapore Bounding Box
    bbox = "1.15,103.55,1.48,104.1"
    
    overpass_query = f"""
    [out:json][timeout:60];
    (
      way["name"~"{query}",i]({bbox});
      relation["name"~"{query}",i]({bbox});
    );
    out geom;
    """
    
    try:
        response = requests.get(overpass_url, params={'data': overpass_query}, timeout=65)
        print(f"Response Status: {response.status_code}")
        if response.status_code != 200:
            print(f"Response Text: {response.text}")
            
        data = response.json()
        return data
    except Exception as e:
        print(f"Overpass Error: {e}")
        return None

def process_and_sample(data, sample_dist_km=2.0):
    """
    Extract all points, sort/order them (hard for disjoint segments), 
    or just spatial sample them.
    Simpler approach for 'Rail Corridor' which is roughly linear:
    1. Collect all points.
    2. Pick a starting point (e.g. northernmost).
    3. Greedily pick next point that is > sample_dist_km away but closest to current.
    """
    if not data or 'elements' not in data:
        return []
        
    all_points = []
    
    print(f"Found {len(data['elements'])} elements (ways/relations).")
    
    for el in data['elements']:
        if 'geometry' in el:
            for pt in el['geometry']:
                all_points.append([pt['lat'], pt['lon']])
        elif 'members' in el:
            # For relations, members might have geometry if 'out geom' was used and they are ways
            for member in el['members']:
                if 'geometry' in member:
                    for pt in member['geometry']:
                        all_points.append([pt['lat'], pt['lon']])

    if not all_points:
        print("No geometry points found.")
        return []
        
    points = np.array(all_points)
    print(f"Total raw points: {len(points)}")
    
    # Heuristic Sorting/Sampling for Linear Features
    # 1. Remove duplicates (or very close points)
    # Simple rounding for unique check
    _, unique_idx = np.unique(points.round(decimals=4), axis=0, return_index=True)
    points = points[unique_idx]
    
    # 2. Sort by Latitude (simple for North-South Rail Corridor)
    # Rail corridor is roughly North-South. 
    # But if it curves, this might break. 
    # Better: Graph traversal or Nearest Neighbor hopping.
    
    # Let's try NN Hopping:
    # Start at one extreme (e.g. Max Lat - Woodlands)
    start_idx = np.argmax(points[:, 0]) 
    
    ordered_path = [points[start_idx]]
    remaining_indices = set(range(len(points)))
    remaining_indices.remove(start_idx)
    
    current_idx = start_idx
    
    # This is O(N^2), but N is small (< 5000 usually)
    # Actually, we don't need to order EVERY point, just sample.
    
    sampled_points = [points[start_idx]]
    last_sample = points[start_idx]
    
    # Iterative grabbing
    # We want points that follow the path.
    # Just sorting by Latitude might be surprisingly effective for Rail Corridor.
    # Let's try Sorting by Latitude first as a robust fallback for vertical routes.
    
    sorted_points = points[np.argsort(points[:, 0])[::-1]] # North to South
    
    final_samples = []
    if len(sorted_points) > 0:
        final_samples.append(sorted_points[0])
        
    for i in range(1, len(sorted_points)):
        curr = sorted_points[i]
        last = final_samples[-1]
        
        # Dist in km
        dist = haversine(last[0], last[1], curr[0], curr[1])
        
        if dist >= sample_dist_km:
            final_samples.append(curr)
            
    return final_samples

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon/2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
    return R * c

if __name__ == "__main__":
    data = fetch_osm_path("Rail Corridor")
    samples = process_and_sample(data, sample_dist_km=2.0)
    
    print("\n--- Sampled Points (North to South) ---")
    for i, p in enumerate(samples):
        print(f"Point {i+1}: {p[0]:.4f}, {p[1]:.4f} (Approx Location)")
    
    print(f"\nTotal Samples: {len(samples)}")
