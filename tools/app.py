import streamlit as st
import pandas as pd
import torch
import os
from datetime import datetime
import plotly.express as px
from predict import load_system, get_input_data, DEVICE

# --- Page Config ---
st.set_page_config(
    page_title="SG Rainfall AI",
    page_icon="🌧️",
    layout="wide"
)

st.title("🌧️ Singapore Rainfall AI Forecast")
st.markdown("Fusing **Himawari-9 Satellite** & **Ground Sensors** for hyper-local prediction.")

# --- Singleton Model Load ---
@st.cache_resource
def get_model_and_data():
    return load_system()

try:
    with st.spinner("Loading AI Brain..."):
        model, df = get_model_and_data()
except FileNotFoundError:
    st.error("Model not found! Please run train.py first.")
    st.stop()

# --- Sidebar Controls ---
st.sidebar.header("🕹️ Controls")
# Time selection
all_times = df['timestamp'].sort_values().unique()
# Default to latest
start_idx = len(all_times) - 1
selected_ts = st.sidebar.select_slider(
    "Select Time (Historical Replay)",
    options=all_times,
    value=all_times[start_idx]
)

# Convert numpy.datetime64 to pd.Timestamp for proper type handling
target_time = pd.Timestamp(selected_ts)

st.sidebar.markdown(f"**Target Time:** {target_time.strftime('%Y-%m-%d %H:%M')}")

# --- Main Logic ---

# 1. Get List of Sensors & Prepare Map Data
sensors = df[['sensor_id', 'sensor_id']].drop_duplicates()
# We need lat/lon. Since our csv doesn't store static lat/lon (simulation logic in create_dummy_data does),
# we need to recover them or join.
# For simplicity in this mock, let's hardcode the locations from create_dummy_data.py
# If you used fetch_and_process_gov_data, you might need a separate metadata file.
# Let's derive a simple mapping for the demo if 'lat' col exists, else mock.

sensor_meta = {
    "S24":  {"name": "Changi", "lat": 1.3678, "lon": 103.9826},
    "S44":  {"name": "Jurong", "lat": 1.3455, "lon": 103.6806},
    "S50":  {"name": "Clementi", "lat": 1.3337, "lon": 103.7768},
    "S109": {"name": "Ang Mo Kio", "lat": 1.3764, "lon": 103.8492}
}

# --- Batch Prediction for All Sensors ---
results = []

progress_bar = st.progress(0)
for i, (sid, meta) in enumerate(sensor_meta.items()):
    # Predict
    sat_in, sensor_in = get_input_data(df, sid, target_time)
    
    pred_val = 0.0
    status = "Unknown"
    
    if sat_in is not None and sensor_in is not None:
        with torch.no_grad():
            prediction = model(sat_in.to(DEVICE), sensor_in.to(DEVICE))
            pred_val = prediction.item()
            
    # Interpretation
    if pred_val < 0.1: status = "Clear"
    elif pred_val < 2.0: status = "Light Rain"
    else: status = "Storm"

    results.append({
        "sensor_id": sid,
        "name": meta["name"],
        "lat": meta["lat"],
        "lon": meta["lon"],
        "rain_pred": max(0, pred_val), # Clamp negative
        "status": status
    })
    progress_bar.progress((i + 1) / len(sensor_meta))

progress_bar.empty()
pred_df = pd.DataFrame(results)

# --- Visualization ---

col1, col2 = st.columns([3, 1])

with col1:
    st.subheader("🗺️ Live Prediction Map")
    
    # Simple Map
    fig = px.scatter_mapbox(
        pred_df, 
        lat="lat", lon="lon",
        color="rain_pred",
        size="rain_pred",
        size_max=30,
        hover_name="name",
        hover_data={"status": True, "rain_pred": ":.2f"},
        color_continuous_scale="Bluered",
        range_color=[0, 10],
        zoom=10,
        height=500
    )
    fig.update_layout(mapbox_style="carto-positron")
    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("📊 Forecast Board")
    for _, row in pred_df.iterrows():
        color = "green"
        if row['status'] == "Light Rain": color = "orange"
        if row['status'] == "Storm": color = "red"
        
        st.markdown(f"""
        **{row['name']}**  
        :{color}[{row['status']}] ({row['rain_pred']:.2f} mm)
        <hr style='margin: 5px 0'>
        """, unsafe_allow_html=True)

# --- Debug Info ---
with st.expander("🛠️ Debug Info"):
    st.write("Current Time:", target_time)
    st.write("Device:", DEVICE)
    st.dataframe(pred_df)
