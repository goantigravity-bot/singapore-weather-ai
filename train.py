import torch
import torch.nn as nn
import torch.optim as optim
from weather_fusion_model import WeatherFusionNet
from weather_dataset import get_dataloaders
import os

# --- Hyperparameters ---
BATCH_SIZE = 4
LEARNING_RATE = 1e-3

# 🆕 动态Epochs配置
EPOCHS_INITIAL = 30      # 首次训练
EPOCHS_INCREMENTAL = 5   # 增量训练（微调）

# 支持环境变量覆盖
EPOCHS_INITIAL = int(os.environ.get('EPOCHS_INITIAL', EPOCHS_INITIAL))
EPOCHS_INCREMENTAL = int(os.environ.get('EPOCHS_INCREMENTAL', EPOCHS_INCREMENTAL))
if torch.cuda.is_available():
    DEVICE = torch.device("cuda")
elif torch.backends.mps.is_available():
    DEVICE = torch.device("mps")
    print("Using Apple Metal Performance Shaders (MPS)")
else:
    DEVICE = torch.device("cpu")
print(f"Using device: {DEVICE}")

# --- Paths ---
# CSV_PATH = "dummy_data/sensor_readings.csv"
# SAT_DIR = "dummy_data/satellite"
CSV_PATH = "real_sensor_data.csv"
SAT_DIR = "satellite_data"
MODEL_SAVE_PATH = "weather_fusion_model.pth"

def train_model():
    # 1. Data
    print("Loading Data...")
    train_loader, val_loader = get_dataloaders(CSV_PATH, SAT_DIR, batch_size=BATCH_SIZE)
    
    # 2. Model
    model = WeatherFusionNet(sat_channels=1, sensor_features=4, prediction_dim=1) # Sat channel=1 because we use B13 (Infrared) only
    
    # 🆕 增量学习: 检查是否存在已训练模型
    if os.path.exists(MODEL_SAVE_PATH):
        print(f"\n🔄 检测到已有模型: {MODEL_SAVE_PATH}")
        print("   尝试增量学习加载...")
        try:
            # Smart Loading Logic
            saved_state = torch.load(MODEL_SAVE_PATH, map_location=DEVICE)
            model_state = model.state_dict()
            
            # Check for shape mismatch in SensorEncoder (3 vs 4 features)
            pixel_layer_weight = 'sensor_encoder.lstm.weight_ih_l0'
            
            if pixel_layer_weight in saved_state and pixel_layer_weight in model_state:
                saved_shape = saved_state[pixel_layer_weight].shape
                model_shape = model_state[pixel_layer_weight].shape
                
                # Default shape for LSTM weight_ih_l0 is (4*hidden_size, input_size)
                # saved: (256, 3), model: (256, 4) if hidden=64
                if saved_shape != model_shape:
                    print(f"   ⚠️  Layer Shape Mismatch detected: {pixel_layer_weight}")
                    print(f"   Saved: {saved_shape} | Current: {model_shape}")
                    
                    if saved_shape[0] == model_shape[0] and saved_shape[1] < model_shape[1]:
                        print("   💡 Performing Smart Adaptation (3->4 features)...")
                        # Copy existing weights
                        new_weight = model_state[pixel_layer_weight].clone()
                        # Copy old weights to the corresponding slice
                        # Assuming inputs were [Temp, Hum, Rain] and now [Temp, Hum, Rain, PM2.5]
                        # We copy the first 3 columns
                        new_weight[:, :saved_shape[1]] = saved_state[pixel_layer_weight]
                        
                        # Use initialized random weights for the new column(s) (already in new_weight)
                        # Optional: Initialize with smaller variance or zero to not disrupt training initially?
                        # Using model's default init (which is usually uniform/xavier) is fine.
                        
                        # Update the saved state dict to inject modified weight
                        saved_state[pixel_layer_weight] = new_weight
                        
                        # Do the same for bias? LSTM bias is (4*hidden,), it doesn't depend on input size.
                        # Wait, weight_ih_l0 is input-hidden weights. bias_ih_l0 is bias. 
                        # Bias shape depends only on hidden size, so it should match if hidden size didn't change.
                        print("   ✅ Smart adaptation applied to weights.")
            
            # Load with strict=False to allow for minor mismatches if any, but our fix should make it perfect match
            # But let's verify keys first.
            model.load_state_dict(saved_state, strict=False)
            EPOCHS = EPOCHS_INCREMENTAL
            print(f"   ✅ 模型加载成功 (增量模式)，将训练 {EPOCHS} epochs")
            
        except Exception as e:
            print(f"   ⚠️  模型加载失败 (Error: {e})")
            print(f"   将从头开始训练 {EPOCHS_INITIAL} epochs")
            EPOCHS = EPOCHS_INITIAL
    else:
        print(f"\n🆕 首次训练，从头开始")
        EPOCHS = EPOCHS_INITIAL
        print(f"   将训练 {EPOCHS} epochs")
    
    model.to(DEVICE)
    
    # 3. Loss & Optimizer
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    
    print(f"\n{'='*60}")
    print(f"训练配置:")
    print(f"  - 模式: {'增量学习' if os.path.exists(MODEL_SAVE_PATH) else '首次训练'}")
    print(f"  - Epochs: {EPOCHS}")
    print(f"  - Batch Size: {BATCH_SIZE}")
    print(f"  - Learning Rate: {LEARNING_RATE}")
    print(f"  - Device: {DEVICE}")
    print(f"{'='*60}\n")
    
    print("Starting Training...")
    best_loss = float('inf')
    
    # Track history for plotting later if needed
    history = {'train_loss': [], 'val_loss': [], 'train_mae': [], 'val_mae': []}
    
    for epoch in range(EPOCHS):
        model.train()
        running_loss = 0.0
        running_mae = 0.0
        
        for batch_idx, (sat, sensor, target) in enumerate(train_loader):
            sat, sensor, target = sat.to(DEVICE), sensor.to(DEVICE), target.to(DEVICE)
            
            optimizer.zero_grad()
            
            # Forward
            outputs = model(sat, sensor)
            loss = criterion(outputs, target)
            
            # Calculate MAE (for human readability)
            mae = torch.mean(torch.abs(outputs - target))
            
            # Backward
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
            running_mae += mae.item()
        
        avg_train_loss = running_loss / len(train_loader)
        avg_train_mae = running_mae / len(train_loader)
        
        # Validation
        model.eval()
        val_loss = 0.0
        val_mae = 0.0
        with torch.no_grad():
            for sat, sensor, target in val_loader:
                sat, sensor, target = sat.to(DEVICE), sensor.to(DEVICE), target.to(DEVICE)
                outputs = model(sat, sensor)
                loss = criterion(outputs, target)
                mae = torch.mean(torch.abs(outputs - target))
                
                val_loss += loss.item()
                val_mae += mae.item()
        
        avg_val_loss = val_loss / len(val_loader)
        avg_val_mae = val_mae / len(val_loader)
        
        history['train_loss'].append(avg_train_loss)
        history['val_loss'].append(avg_val_loss)
        
        print(f"Epoch [{epoch+1}/{EPOCHS}] "
              f"Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f} || "
              f"MAE: {avg_train_mae:.4f} | Val MAE: {avg_val_mae:.4f}", flush=True)
        
        # Save Best (based on Val Loss)
        if avg_val_loss < best_loss:
            best_loss = avg_val_loss
            torch.save(model.state_dict(), MODEL_SAVE_PATH)
            # print("  Model Saved config.")

    print(f"\nTraining Complete. Best Val Loss: {best_loss:.4f}")
    print(f"Model saved to: {MODEL_SAVE_PATH}")
    
    # Save Metrics for Dashboard
    metrics = {
        "best_val_loss": best_loss,
        "final_epoch": EPOCHS,
        "last_train_mae": avg_train_mae,
        "last_val_mae": avg_val_mae,
        "rmse": best_loss ** 0.5,
        "success": True
    }
    with open("training_metrics.json", "w") as f:
        import json
        json.dump(metrics, f, indent=2)
    
    print("Force exiting to prevent MPS hang...")
    import sys
    sys.exit(0)

if __name__ == "__main__":
    if not os.path.exists(CSV_PATH):
        print("Error: Dummy data not found. Please run 'create_dummy_data.py' first.")
    else:
        train_model()
