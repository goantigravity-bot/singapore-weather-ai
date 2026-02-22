import torch
import torch.nn as nn
import torch.optim as optim
from torch.amp import autocast, GradScaler
from weather_fusion_model import WeatherFusionNet
from weather_dataset import get_dataloaders
import os
import time
import logging
import json

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class WeightedMSELoss(nn.Module):
    """降雨数据极度不平衡(99%无雨)，普通MSE会让模型学到"永远预测均值"的捷径。
    给有雨样本更高权重，迫使模型认真学习降雨特征。"""
    def __init__(self, rain_threshold=0.1, rain_weight=10.0):
        super().__init__()
        self.rain_threshold = rain_threshold
        self.rain_weight = rain_weight

    def forward(self, pred, target):
        weights = torch.where(
            target > self.rain_threshold,
            torch.tensor(self.rain_weight, device=pred.device),
            torch.tensor(1.0, device=pred.device)
        )
        return torch.mean(weights * (pred - target) ** 2)

# --- Hyperparameters ---
LEARNING_RATE = 1e-3

# 根据设备动态调整 Batch Size
# GPU 并行计算能力强，大 batch 提升吞吐量；CPU 保持较小 batch 避免内存压力
if torch.cuda.is_available():
    BATCH_SIZE = 256  # T4 有 16GB 显存，大 batch 减少 CPU→GPU 传输次数
elif torch.backends.mps.is_available():
    BATCH_SIZE = 16
else:
    BATCH_SIZE = 8

# 🆕 动态Epochs配置
EPOCHS_INITIAL = 30      # 首次训练
EPOCHS_INCREMENTAL = 15  # 增量训练（Weighted Loss 需要更多轮数收敛）

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
# --- Paths ---
# Docker environment uses /app/data
HOME_DIR = os.path.expanduser("~")
WORK_DIR = os.environ.get("WORK_DIR", os.path.join(HOME_DIR, "training"))

# Docker Path Overrides
if os.path.exists("/app/data"):
    WORK_DIR = "/app/data"
    
CSV_PATH = os.environ.get("CSV_PATH", os.path.join(WORK_DIR, "real_sensor_data.csv"))
SAT_DIR = os.environ.get("SAT_DIR", os.path.join(WORK_DIR, "processed_data"))
# Model is saved to /app/models or root?
# training_service.py expects to upload from somewhere.
# Let's save to current dir or specific output dir.
MODEL_SAVE_PATH = "weather_fusion_model.pth" 


def train_model():
    train_start_time = time.time()

    # 1. Data
    logger.info(f"Loading Data from {CSV_PATH} and {SAT_DIR}...")
    if not os.path.exists(CSV_PATH):
        logger.error(f"❌ Sensor data not found at {CSV_PATH}")
        return

    train_loader, val_loader = get_dataloaders(CSV_PATH, SAT_DIR, batch_size=BATCH_SIZE)
    
    if len(train_loader) == 0:
        logger.error("❌ Train loader is empty! No data found for training.")
        return
        
    logger.info(f"✅ Data Loaded: {len(train_loader)} batches")

    
    # 2. Model
    model = WeatherFusionNet(sat_channels=3, sensor_features=7, coord_dim=2, prediction_dim=1)
    
    # 增量学习: 检查是否存在已训练模型
    if os.path.exists(MODEL_SAVE_PATH):
        logger.info(f"🔄 检测到已有模型: {MODEL_SAVE_PATH}")
        try:
            saved_state = torch.load(MODEL_SAVE_PATH, map_location=DEVICE)
            model_state = model.state_dict()
            
            # 检查 LSTM 输入维度变化（3→4 特征的兼容处理）
            pixel_layer_weight = 'sensor_encoder.lstm.weight_ih_l0'
            if pixel_layer_weight in saved_state and pixel_layer_weight in model_state:
                saved_shape = saved_state[pixel_layer_weight].shape
                model_shape = model_state[pixel_layer_weight].shape
                
                if saved_shape != model_shape:
                    logger.warning(f"Layer Shape Mismatch: {pixel_layer_weight} saved={saved_shape} current={model_shape}")
                    if saved_shape[0] == model_shape[0] and saved_shape[1] < model_shape[1]:
                        new_weight = model_state[pixel_layer_weight].clone()
                        new_weight[:, :saved_shape[1]] = saved_state[pixel_layer_weight]
                        saved_state[pixel_layer_weight] = new_weight
                        logger.info("Smart adaptation applied to weights")
            
            # 过滤掉所有维度不匹配的层（如 coord_dim 变化导致 fusion_head 不兼容）
            compatible_state = {}
            skipped = []
            for k, v in saved_state.items():
                if k in model_state and v.shape == model_state[k].shape:
                    compatible_state[k] = v
                else:
                    skipped.append(k)
            if skipped:
                logger.warning(f"跳过 {len(skipped)} 个不兼容层: {skipped}")
            
            model.load_state_dict(compatible_state, strict=False)
            EPOCHS = EPOCHS_INCREMENTAL
            logger.info(f"✅ 模型加载成功 (增量模式，{len(compatible_state)}/{len(saved_state)} 层兼容)，将训练 {EPOCHS} epochs")
            
        except Exception as e:
            logger.error(f"模型加载失败: {e}，从头开始训练 {EPOCHS_INITIAL} epochs")
            EPOCHS = EPOCHS_INITIAL
    else:
        logger.info(f"🆕 首次训练，从头开始 {EPOCHS_INITIAL} epochs")
        EPOCHS = EPOCHS_INITIAL
    
    model.to(DEVICE)
    
    # 3. Loss, Optimizer, Scheduler
    RAIN_WEIGHT = float(os.environ.get('RAIN_WEIGHT', 10.0))
    criterion = WeightedMSELoss(rain_threshold=0.1, rain_weight=RAIN_WEIGHT)
    optimizer = optim.Adam(model.parameters(), lr=LEARNING_RATE)
    
    # LR Scheduler: val_loss 停滞时自动衰减学习率，帮助精细收敛
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=2, min_lr=1e-6
    )
    
    # Mixed Precision: 仅在 CUDA 上启用，FP16 可加速 ~2x 并节省显存
    use_amp = (DEVICE.type == 'cuda')
    scaler = GradScaler(enabled=use_amp)
    
    # Early Stopping: 避免 val_loss 不再下降后继续浪费算力
    EARLY_STOPPING_PATIENCE = int(os.environ.get('EARLY_STOPPING_PATIENCE', 5))
    no_improve_count = 0
    
    logger.info(f"\n{'='*60}")
    logger.info(f"训练配置:")
    logger.info(f"  - 模式: {'增量学习' if os.path.exists(MODEL_SAVE_PATH) else '首次训练'}")
    logger.info(f"  - Epochs: {EPOCHS} (Early Stop patience={EARLY_STOPPING_PATIENCE})")
    logger.info(f"  - Batch Size: {BATCH_SIZE}")
    logger.info(f"  - Learning Rate: {LEARNING_RATE}")
    logger.info(f"  - Loss: WeightedMSE (rain_weight={RAIN_WEIGHT})")
    logger.info(f"  - Device: {DEVICE}")
    logger.info(f"  - AMP (Mixed Precision): {use_amp}")
    logger.info(f"{'='*60}")
    
    logger.info("Starting Training...")
    best_loss = float('inf')
    actual_epochs = 0
    total_train_samples = 0
    
    history = {'train_loss': [], 'val_loss': [], 'train_mae': [], 'val_mae': []}
    
    for epoch in range(EPOCHS):
        epoch_start = time.time()
        model.train()
        running_loss = 0.0
        running_mae = 0.0
        epoch_samples = 0
        
        for batch_idx, (sat, sensor, coord, target) in enumerate(train_loader):
            sat, sensor, coord, target = sat.to(DEVICE), sensor.to(DEVICE), coord.to(DEVICE), target.to(DEVICE)
            
            optimizer.zero_grad()
            
            # Mixed Precision 前向传播
            with autocast(device_type=DEVICE.type, enabled=use_amp):
                outputs = model(sat, sensor, coord)
                loss = criterion(outputs, target)
            
            mae = torch.mean(torch.abs(outputs - target))
            
            # Scaled 反向传播（AMP 防止梯度下溢）
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            
            running_loss += loss.item()
            running_mae += mae.item()
            epoch_samples += target.size(0)
        
        avg_train_loss = running_loss / len(train_loader)
        avg_train_mae = running_mae / len(train_loader)
        total_train_samples += epoch_samples
        
        # Validation
        model.eval()
        val_loss = 0.0
        val_mae = 0.0
        # 降雨二分类准确率：预测值和实际值是否同时 > 阈值（有雨）或同时 <= 阈值（无雨）
        rain_correct = 0
        rain_total = 0
        RAIN_THRESHOLD = 0.1
        with torch.no_grad():
            for sat, sensor, coord, target in val_loader:
                sat, sensor, coord, target = sat.to(DEVICE), sensor.to(DEVICE), coord.to(DEVICE), target.to(DEVICE)
                with autocast(device_type=DEVICE.type, enabled=use_amp):
                    outputs = model(sat, sensor, coord)
                    loss = criterion(outputs, target)
                mae = torch.mean(torch.abs(outputs - target))
                val_loss += loss.item()
                val_mae += mae.item()
                # 二分类准确率统计
                pred_rain = (outputs > RAIN_THRESHOLD).float()
                actual_rain = (target > RAIN_THRESHOLD).float()
                rain_correct += (pred_rain == actual_rain).sum().item()
                rain_total += target.numel()
        
        avg_val_loss = val_loss / len(val_loader)
        avg_val_mae = val_mae / len(val_loader)
        rain_accuracy = rain_correct / rain_total if rain_total > 0 else 0.0
        actual_epochs = epoch + 1
        
        history['train_loss'].append(avg_train_loss)
        history['val_loss'].append(avg_val_loss)
        
        # LR Scheduler 根据 val_loss 自动调整学习率
        scheduler.step(avg_val_loss)
        current_lr = optimizer.param_groups[0]['lr']
        
        epoch_time = time.time() - epoch_start
        logger.info(
            f"Epoch [{epoch+1}/{EPOCHS}] "
            f"Time: {epoch_time:.1f}s | "
            f"Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f} || "
            f"MAE: {avg_train_mae:.4f} | Val MAE: {avg_val_mae:.4f} | "
            f"LR: {current_lr:.1e}"
        )
        
        # Early Stopping + Best Model 保存
        if avg_val_loss < best_loss:
            best_loss = avg_val_loss
            no_improve_count = 0
            torch.save(model.state_dict(), MODEL_SAVE_PATH)
        else:
            no_improve_count += 1
            if no_improve_count >= EARLY_STOPPING_PATIENCE:
                logger.info(
                    f"⏹️ Early Stopping: val_loss 连续 {EARLY_STOPPING_PATIENCE} epochs 未改善 "
                    f"(best={best_loss:.4f}, current={avg_val_loss:.4f})"
                )
                break

    total_time = time.time() - train_start_time
    logger.info(f"\nTraining Complete in {total_time:.1f}s ({actual_epochs} epochs). Best Val Loss: {best_loss:.4f}")
    logger.info(f"Model saved to: {MODEL_SAVE_PATH}")
    
    # Save Metrics for Dashboard
    metrics = {
        "best_val_loss": best_loss,
        "final_epoch": actual_epochs,
        "max_epochs": EPOCHS,
        "last_train_mae": avg_train_mae,
        "last_val_mae": avg_val_mae,
        "rmse": best_loss ** 0.5,
        "rain_accuracy": rain_accuracy,
        "total_train_samples": total_train_samples,
        "training_time_seconds": round(total_time, 1),
        "early_stopped": no_improve_count >= EARLY_STOPPING_PATIENCE,
        "device": str(DEVICE),
        "batch_size": BATCH_SIZE,
        "rain_weight": RAIN_WEIGHT,
        "success": True
    }
    
    metrics_path = os.path.abspath("training_metrics.json")
    try:
        with open(metrics_path, "w") as f:
            json.dump(metrics, f, indent=2)
        logger.info(f"✅ Metrics saved to: {metrics_path}")
    except Exception as e:
        logger.error(f"❌ Failed to save metrics to {metrics_path}: {e}")
    
    logger.info("Force exiting to prevent MPS hang...")
    import sys
    sys.exit(0)

if __name__ == "__main__":
    if not os.path.exists(CSV_PATH):
        print("Error: Sensor data not found at", CSV_PATH)
        import sys
        sys.exit(1)
    else:
        train_model()
