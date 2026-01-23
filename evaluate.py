import torch
import torch.nn as nn
from weather_fusion_model import WeatherFusionNet
from weather_dataset import get_dataloaders
import matplotlib
matplotlib.use('Agg') # Headless mode for Cloud/Server
import matplotlib.pyplot as plt
import numpy as np
import os

# --- Config ---
MODEL_PATH = "weather_fusion_model.pth"
CSV_PATH = "real_sensor_data.csv"
SAT_DIR = "satellite_data"
DEVICE = torch.device("cpu") # Eval on CPU is fine usually

def evaluate_model():
    # Set seed for reproducibility relative to train.py (if train uses same seed)
    torch.manual_seed(42)
    
    # 1. Load Data (Validation Set Only)
    _, val_loader = get_dataloaders(CSV_PATH, SAT_DIR, batch_size=1, split=0.8)
    
    # 2. Load Model
    model = WeatherFusionNet(sat_channels=1, sensor_features=3, prediction_dim=1)
    if os.path.exists(MODEL_PATH):
        model.load_state_dict(torch.load(MODEL_PATH, map_location=DEVICE))
        print(f"Loaded model from {MODEL_PATH}")
    else:
        print("Model file not found! Train first.")
        return
    
    model.to(DEVICE)
    model.eval()
    
    predictions = []
    actuals = []
    
    print("Running evaluation...")
    with torch.no_grad():
        for sat, sensor, target in val_loader:
            sat, sensor = sat.to(DEVICE), sensor.to(DEVICE)
            output = model(sat, sensor)
            
            # Simple clamping to avoid negative rain
            pred_val = max(0.0, output.item())
            
            predictions.append(pred_val)
            actuals.append(target.item())
            
    # 3. Calculate Metrics
    predictions = np.array(predictions)
    actuals = np.array(actuals)
    
    mae = np.mean(np.abs(predictions - actuals))
    rmse = np.sqrt(np.mean((predictions - actuals)**2))
    
    # Classification Metric (Rain vs No-Rain) threshold 0.1mm
    threshold = 0.1
    pred_rain = predictions > threshold
    true_rain = actuals > threshold
    accuracy = np.mean(pred_rain == true_rain)
    
    print("\n--- Evaluation Results ---")
    print(f"MAE  (Mean Abs Error):   {mae:.4f} mm")
    print(f"RMSE (Root Mean Sq Err): {rmse:.4f} mm")
    print(f"Rain Detection Acc:      {accuracy*100:.2f}% (Threshold {threshold}mm)")
    print("--------------------------")
    
    # 4. Plotting (2 Subplots)
    plt.figure(figsize=(12, 5))
    
    # Plot 1: Time Series (First 100)
    plt.subplot(1, 2, 1)
    plt.plot(actuals[:100], label="Actual", color='blue', alpha=0.7)
    plt.plot(predictions[:100], label="Predicted", color='orange', alpha=0.7, linestyle='--')
    plt.title("Time Series (First 100 samples)")
    plt.xlabel("Sample Index")
    plt.ylabel("Rainfall (mm)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # Plot 2: Scatter (Pred vs Actual)
    plt.subplot(1, 2, 2)
    plt.scatter(actuals, predictions, alpha=0.5, s=10)
    
    # Ideal Diagonal Line
    max_val = max(np.max(actuals), np.max(predictions))
    plt.plot([0, max_val], [0, max_val], 'r--', label="Ideal (y=x)")
    
    plt.title("Correlation: Actual vs Predicted")
    plt.xlabel("Actual Rain (mm)")
    plt.ylabel("Predicted Rain (mm)")
    plt.axis('equal')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    save_path = "evaluation_plot.png"
    plt.savefig(save_path)
    print(f"\nEvaluation Plot saved to: {save_path}")
    print("Open this image to visually assess if points align with the diagonal red line.")

if __name__ == "__main__":
    evaluate_model()
