#!/usr/bin/env python3
"""
Smart Query Interface for Weather AI
Handles Natural Language Processing (Regex/Keywords) and Activity Advice.
"""
import sys
import re
from datetime import datetime, timedelta
import pandas as pd
from predict import fetch_osm_path, process_and_sample_path, predict_ensemble, load_system, get_station_mapping

# --- Configuration ---
ACTIVITY_RULES = {
    'bicycle': {'rain_tolerance': 0.5, 'name': 'Cycling'},
    'ride': {'rain_tolerance': 0.5, 'name': 'Cycling'},
    'bike': {'rain_tolerance': 0.5, 'name': 'Cycling'},
    'run': {'rain_tolerance': 1.0, 'name': 'Running'},
    'jog': {'rain_tolerance': 1.0, 'name': 'Running'},
    'walk': {'rain_tolerance': 0.2, 'name': 'Walking'},
    'hike': {'rain_tolerance': 0.2, 'name': 'Hiking'},
    'picnic': {'rain_tolerance': 0.0, 'name': 'Picnic'},
}

def parse_query(query):
    """
    Parse natural language query to extract:
    - Location (e.g. "rail corridor")
    - Activity (e.g. "ride bicycle")
    - Time Range (e.g. "2 to 5pm", "14:00-17:00")
    """
    query = query.lower()
    
    # 1. Extract Activity
    activity = None
    tolerance = 2.0 # Default High Tolerance
    
    for key, rule in ACTIVITY_RULES.items():
        if key in query:
            activity = rule['name']
            tolerance = rule['rain_tolerance']
            break
            
    if not activity:
        activity = "General Activity"
        
    # 2. Extract Location (Simple Heuristic: Everything after 'at' or 'in' or 'to'?)
    # A better way for this specific demo is known locations + regex
    # Or just assume the user mentions a place.
    # Let's try to find known keywords or use a greedy approach.
    
    known_places = ["rail corridor", "sentosa", "east coast park", "macritchie", "fort canning", "marina bay"]
    location = None
    
    for place in known_places:
        if place in query:
            location = place
            break
            
    if not location:
        # Fallback: Regex for "at [Location]"
        match = re.search(r'(?:at|in|near)\s+([a-z\s]+?)(?:\s+today|\s+tomorrow|\s+from|\s+at\s+\d|$)', query)
        if match:
            location = match.group(1).strip()
    
    if not location:
        location = "Singapore" # Default
        
    # 3. Extract Time Range
    # Supported formats: "2 to 5pm", "14:00-17:00", "2pm - 5pm"
    start_hour = None
    end_hour = None
    
    # Regex for "X to Y pm" or "X-Y"
    # Case A: "2 to 5pm", "2-5pm"
    time_match = re.search(r'(\d{1,2})(?::00)?\s*(?:to|-)\s*(\d{1,2})(?::00)?\s*(am|pm)?', query)
    
    if time_match:
        h1 = int(time_match.group(1))
        h2 = int(time_match.group(2))
        meridiem = time_match.group(3) # pm
        
        # Normalize to 24h
        if meridiem == 'pm':
            if h1 < 12: h1 += 12
            if h2 < 12: h2 += 12
        elif not meridiem:
            # Infer PM if small numbers and "today"? Or just assume 24h if > 12
            if h1 < 10 and h2 < 10: # Likely 2-5 -> 14-17
                 h1 += 12
                 h2 += 12
                 
        start_hour = h1
        end_hour = h2
    else:
        # Default: Now + 3 hours
        now = datetime.now()
        start_hour = now.hour
        end_hour = min(23, now.hour + 3)
        
    return {
        'location': location,
        'activity': activity,
        'tolerance': tolerance,
        'start_hour': start_hour,
        'end_hour': end_hour
    }

def analyze_path_weather(location, start_hour, end_hour, tolerance, model, df, stations_meta):
    """
    Analyze weather along a path for a duration
    """
    print(f"\n🔍 Analyzing '{location}' for {start_hour}:00 - {end_hour}:00...")
    
    # 1. Get Path Points
    points = []
    # Check if it looks like a path
    osm_data = fetch_osm_path(location)
    
    if osm_data:
        points = process_and_sample_path(osm_data, sample_dist_km=2.0)
        print(f"📍 Found {len(points)} key points along the route.")
    else:
        # Fallback: Geocode single point
        # We need geocode logic from predict.py but it's not exposed as `geocode_location` easily?
        # Actually it is `geocode_location` inside predict.py
        from predict import geocode_location
        lat, lon = geocode_location(location)
        if lat and lon:
            points = [[lat, lon]]
            print(f"📍 Analysis for single point ({lat}, {lon})")
        else:
            print("❌ Could not locate.")
            return

    # 2. Iterate Time and Space
    # Since our "Simulation" DB only has data up to valid_timestamp, we can't really predict "Future 5pm" 
    # if our DB ends at "2pm".
    # For this DEMO, we will assume the request is regarding the LATEST AVAILABLE DATA 
    # but we simulate "Forecast" for the requested duration by just using the current prediction logic.
    # In a real system, we'd roll the model forward. Here we effectively check "Current Outlook".
    
    # Reference Time
    ref_time = df['timestamp'].max()
    print(f"🕒 Forecast Reference Time: {ref_time}")
    
    # Analyze
    risk_points = 0
    total_points = len(points)
    max_rain = 0.0
    
    details = []
    
    for i, pt in enumerate(points):
        lat, lon = pt
        res = predict_ensemble(lat, lon, ref_time, model, df, stations_meta)
        
        if res:
            rain = res['rainfall']
            if rain > max_rain:
                max_rain = rain
                
            status_icon = "☁️" if res['status'] == 'Cloudy' else ("🌧️" if 'Rain' in res['status'] else "☀️")
            
            # Risk Check
            if rain > tolerance:
                risk_points += 1
                details.append(f"Pt {i+1}: ⚠️ {res['status']} ({rain:.2f}mm)")
            else:
                 details.append(f"Pt {i+1}: {status_icon} OK")
    
    # Summary
    risk_ratio = risk_points / total_points
    
    print("\n" + "="*40)
    print(f"📢 ADVICE REPORT for {location.upper()}")
    print("="*40)
    
    if risk_ratio > 0.3:
        print(f"❌ NOT RECOMMENDED for {ACTIVITY_RULES.get(location, {}).get('name', 'Outdoor Activity')}")
        print(f"Reason: Rain detected at {risk_ratio*100:.0f}% of the route.")
        print(f"Max Rainfall: {max_rain:.2f}mm")
    elif max_rain > 0.5: # Some rain but < 30% area
        print(f"⚠️ CAUTION ADVISED")
        print(f"Reason: Patchy rain detected. You might get wet.")
    elif max_rain > 0.0:
        print(f"✅ GO AHEAD (Likely Safe)")
        print("Reason: Mostly clear, slight chance of drizzle.")
    else:
        print(f"⭐ PERFECT CONDITIONS")
        print("Reason: No rain detected along the route.")

    print("\nDetails:")
    # Print simplified details (first 5 and last 5 if too many)
    if len(details) > 10:
        for d in details[:5]: print(d)
        print("...")
        for d in details[-5:]: print(d)
    else:
        for d in details: print(d)

def main():
    if len(sys.argv) < 2:
        print("Usage: python smart_query.py 'your query string'")
        return
        
    query = sys.argv[1]
    parsed = parse_query(query)
    
    print("\n🤔 Understanding your query...")
    print(f"   Activity: {parsed['activity']}")
    print(f"   Location: {parsed['location']}")
    print(f"   Time: {parsed['start_hour']}:00 - {parsed['end_hour']}:00")
    
    # Load Model
    model, df = load_system()
    stations_meta = get_station_mapping()
    
    analyze_path_weather(
        parsed['location'], 
        parsed['start_hour'], 
        parsed['end_hour'],
        parsed['tolerance'],
        model, df, stations_meta
    )

if __name__ == "__main__":
    main()
