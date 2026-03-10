#!/usr/bin/env python3
"""
Smart Query Interface for Weather AI
Handles Natural Language Processing (Gemini Flash + Regex fallback) and Activity Advice.
"""
import sys
import re
import logging
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import numpy as np
from predict import fetch_osm_path, process_and_sample_path, predict_ensemble, load_system, get_station_mapping
import gemini_nlu

logger = logging.getLogger(__name__)

# --- Configuration ---
def convert_numpy(obj):
    if isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    if isinstance(obj, dict):
        return {k: convert_numpy(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [convert_numpy(i) for i in obj]
    if hasattr(obj, 'item'):
        return obj.item()
    if hasattr(obj, 'tolist'):
        return obj.tolist()
    return obj

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
    Parse natural language query to extract location, activity, time.
    Strategy: try Gemini Flash first, fall back to regex on failure.
    """
    # --- Try Gemini NLU first ---
    gemini_result = gemini_nlu.extract(query)
    if gemini_result:
        activity_name = gemini_result.get("activity")
        tolerance = 2.0
        if activity_name:
            # Match to ACTIVITY_RULES for rain tolerance
            for key, rule in ACTIVITY_RULES.items():
                if rule['name'] == activity_name:
                    tolerance = rule['rain_tolerance']
                    break
        else:
            activity_name = "General Activity"

        location = gemini_result.get("place") or "Singapore"
        start_hour = gemini_result.get("start_hour")
        end_hour = gemini_result.get("end_hour")

        # Default time if Gemini didn't extract it
        if start_hour is None or end_hour is None:
            now = datetime.now()
            start_hour = now.hour
            end_hour = min(23, now.hour + 3)

        logger.info(f"NLU(gemini): {query!r} → place={location}, activity={activity_name}")
        return {
            'location': location,
            'activity': activity_name,
            'tolerance': tolerance,
            'start_hour': start_hour,
            'end_hour': end_hour,
        }

    # --- Regex fallback ---
    logger.info(f"NLU(regex): Gemini unavailable, using regex for {query!r}")
    q = query.lower()

    # 1. Extract Activity
    activity = None
    tolerance = 2.0
    for key, rule in ACTIVITY_RULES.items():
        if key in q:
            activity = rule['name']
            tolerance = rule['rain_tolerance']
            break
    if not activity:
        activity = "General Activity"

    # 2. Extract Location
    known_places = [
        "rail corridor", "sentosa", "east coast park", "macritchie",
        "fort canning", "marina bay", "botanic gardens", "changi airport",
        "clementi", "woodlands", "ang mo kio", "tuas", "jurong",
        "bishan", "orchard", "newton", "bedok", "tampines",
    ]
    location = None
    for place in known_places:
        if place in q:
            location = place.title()
            break

    if not location:
        match = re.search(
            r'(?:at|in|near|around)\s+([a-z\s]+?)(?:\s+today|\s+tonight|\s+tomorrow|\s+this\s+\w+|\s+from|\s+at\s+\d|$)',
            q,
        )
        if match:
            location = match.group(1).strip().title()

    if not location:
        location = "Singapore"

    # 3. Extract Time Range
    start_hour = None
    end_hour = None
    time_match = re.search(r'(\d{1,2})(?::00)?\s*(?:to|-)\s*(\d{1,2})(?::00)?\s*(am|pm)?', q)
    if time_match:
        h1 = int(time_match.group(1))
        h2 = int(time_match.group(2))
        meridiem = time_match.group(3)
        if meridiem == 'pm':
            if h1 < 12: h1 += 12
            if h2 < 12: h2 += 12
        elif not meridiem:
            if h1 < 10 and h2 < 10:
                h1 += 12
                h2 += 12
        start_hour = h1
        end_hour = h2
    else:
        now = datetime.now()
        start_hour = now.hour
        end_hour = min(23, now.hour + 3)

    return {
        'location': location,
        'activity': activity,
        'tolerance': tolerance,
        'start_hour': start_hour,
        'end_hour': end_hour,
    }

def analyze_path_weather(location, start_hour, end_hour, tolerance, model, df, stations_meta):
    """
    Analyze weather along a path for a duration.
    Returns a dictionary with analysis results.
    """
    # 1. Get Path Points
    points = []
    # Check if it looks like a path
    osm_data = fetch_osm_path(location)
    
    if osm_data:
        points = process_and_sample_path(osm_data, sample_dist_km=2.0)

    # Overpass 无数据 或 路径采样返回空列表 → 降级为 geocoding 单点
    if not points:
        from predict import geocode_location
        lat, lon = geocode_location(location)
        if lat and lon:
            points = [[lat, lon]]
        else:
            return {"error": "Could not locate location"}

    # 2. Iterate Time and Space
    ref_time = df['timestamp'].max()
    
    risk_points = 0
    total_points = len(points)
    max_rain = 0.0
    details = []

    def _predict_point(args):
        """单点推理 worker，返回 (index, lat, lon, result)"""
        i, pt = args
        lat, lon = pt
        try:
            res = predict_ensemble(lat, lon, ref_time, model, df, stations_meta)
        except Exception as e:
            # 单点失败不影响其他点，返回 None 让汇总阶段跳过
            logger.warning(f"predict_ensemble failed for point {i} ({lat},{lon}): {e}")
            res = None
        return i, float(lat), float(lon), res

    # 单点不走线程池（避免额外开销），多点并行推理
    # max_workers=3 匹配 t3.small 2 vCPU，避免过度线程竞争
    if total_points <= 1:
        raw_results = [_predict_point((0, points[0]))]
    else:
        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                raw_results = list(pool.map(_predict_point, enumerate(points)))
        except Exception as e:
            # 线程池失败时降级为串行执行
            logger.warning(f"ThreadPool failed, falling back to serial: {e}")
            raw_results = [_predict_point((i, pt)) for i, pt in enumerate(points)]

    # 按 point_index 顺序组装结果
    for i, lat, lon, res in sorted(raw_results, key=lambda x: x[0]):
        if res:
            rain = res['rainfall']
            if rain > max_rain:
                max_rain = rain
                
            status_icon = "☁️" if res['status'] == 'Cloudy' else ("🌧️" if 'Rain' in res['status'] else "☀️")
            
            is_risky = rain > tolerance
            if is_risky:
                risk_points += 1
                
            details.append({
                "point_index": i + 1,
                "lat": lat,
                "lon": lon,
                "status": res['status'],
                "rainfall": float(f"{rain:.2f}"),
                "icon": status_icon,
                "is_risky": bool(is_risky),
                "confidence": res.get('confidence', 0.5)
            })
    
    # Summary
    risk_ratio = risk_points / total_points if total_points > 0 else 0
    
    recommendation = ""
    reason = ""
    status_color = "green" # green, orange, red
    
    activity_name = ACTIVITY_RULES.get(location, {}).get('name', 'Outdoor Activity') # This might be wrong key usage, fix in main
    
    if risk_ratio > 0.3:
        recommendation = "NOT RECOMMENDED"
        reason = f"Rain detected at {risk_ratio*100:.0f}% of the route."
        status_color = "red"
    elif max_rain > 0.5: # Some rain but < 30% area
        recommendation = "CAUTION ADVISED"
        reason = "Patchy rain detected. You might get wet."
        status_color = "orange"
    elif max_rain > 0.0:
        recommendation = "GO AHEAD"
        reason = "Mostly clear, slight chance of drizzle."
        status_color = "green"
    else:
        recommendation = "PERFECT CONDITIONS"
        reason = "No rain detected along the route."
        status_color = "green"

    final_result = {
        "location": location,
        "recommendation": recommendation,
        "reason": reason,
        "status_color": status_color,
        "max_rainfall": max_rain,
        "points_analyzed": total_points,
        "details": details
    }
    
    return convert_numpy(final_result)

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
    
    result = analyze_path_weather(
        parsed['location'], 
        parsed['start_hour'], 
        parsed['end_hour'],
        parsed['tolerance'],
        model, df, stations_meta
    )
    
    if "error" in result:
        print(f"❌ {result['error']}")
        return

    print("\n" + "="*40)
    print(f"📢 ADVICE REPORT for {result['location'].upper()}")
    print("="*40)
    
    print(f"Result: {result['recommendation']}")
    print(f"Reason: {result['reason']}")
    
    print("\nDetails:")
    for d in result['details'][:5]:
        print(f"Pt {d['point_index']}: {d['icon']} {d['status']} ({d['rainfall']}mm)")
    if len(result['details']) > 5:
        print("...")

if __name__ == "__main__":
    main()
