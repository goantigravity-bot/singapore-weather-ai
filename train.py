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
        print("   使用增量学习模式（微调）")
        try:
            model.load_state_dict(torch.load(MODEL_SAVE_PATH, map_location=DEVICE))
            EPOCHS = EPOCHS_INCREMENTAL
            print(f"   ✅ 模型加载成功，将训练 {EPOCHS} epochs")
        except Exception as e:
            print(f"   ⚠️  模型加载失败: {e}")
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
              f"MAE: {avg_train_mae:.4f} | Val MAE: {avg_val_mae:.4f}")
        
        # Save Best (based on Val Loss)
        if avg_val_loss < best_loss:
            best_loss = avg_val_loss
            torch.save(model.state_dict(), MODEL_SAVE_PATH)
            # print("  Model Saved config.")

    print(f"\nTraining Complete. Best Val Loss: {best_loss:.4f}")
    print(f"Model saved to: {MODEL_SAVE_PATH}")

if __name__ == "__main__":
    if not os.path.exists(CSV_PATH):
        print("Error: Dummy data not found. Please run 'create_dummy_data.py' first.")
    else:
        train_model()
