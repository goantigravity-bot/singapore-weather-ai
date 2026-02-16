"""
compare_all_rounds.py — 用 1.0mm 阈值对比 Baseline / R1 / R4 全部变体

执行: python3 compare_all_rounds.py
"""
import torch
import torch.nn as nn
import numpy as np
import time
import logging
from weather_dataset import WeatherDataset, get_dataloaders, PATCH_SIZE, IMG_SIZE

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RAIN_THRESHOLD = 1.0  # mm
EPOCHS = 50
BATCH_SIZE = 32
LR = 1e-3

# =====================================================================
# 模型定义（内联，避免修改主文件）
# =====================================================================

class SpatialAttention(nn.Module):
    def __init__(self, in_channels):
        super().__init__()
        self.attn = nn.Sequential(nn.Conv2d(in_channels, 1, 1), nn.Sigmoid())
    def forward(self, x):
        return (x * self.attn(x)).mean(dim=[2, 3])


def make_baseline():
    """Baseline: 3层 CNN + GAP（无 Attention），128×128 全图"""
    class Model(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv2d(1, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            )
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.sat_fc = nn.Linear(64, 128)
            self.lstm = nn.LSTM(7, 128, batch_first=True)
            self.sensor_fc = nn.Linear(128, 64)
            self.head = nn.Sequential(nn.Linear(192, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 1))
        def forward(self, sat, sensor):
            x = self.conv(sat)
            x = self.pool(x).squeeze(-1).squeeze(-1)
            sat_feat = self.sat_fc(x)
            _, (h, _) = self.lstm(sensor)
            sensor_feat = self.sensor_fc(h[-1])
            return self.head(torch.cat((sat_feat, sensor_feat), dim=1))
    return Model()


def make_r1():
    """R1: 3层 CNN + Spatial Attention，128×128 全图"""
    class Model(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv2d(1, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            )
            self.attention = SpatialAttention(64)
            self.sat_fc = nn.Linear(64, 128)
            self.lstm = nn.LSTM(7, 128, batch_first=True)
            self.sensor_fc = nn.Linear(128, 64)
            self.head = nn.Sequential(nn.Linear(192, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 1))
        def forward(self, sat, sensor):
            x = self.conv(sat)
            x = self.attention(x)
            sat_feat = self.sat_fc(x)
            _, (h, _) = self.lstm(sensor)
            sensor_feat = self.sensor_fc(h[-1])
            return self.head(torch.cat((sat_feat, sensor_feat), dim=1))
    return Model()


def make_r2():
    """R2: 5层深 CNN + Spatial Attention（原用 128×128，此处用 32×32 patch）"""
    class Model(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv2d(1, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(64, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
                nn.Conv2d(128, 128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
            )
            self.attention = SpatialAttention(128)
            self.sat_fc = nn.Linear(128, 128)
            self.lstm = nn.LSTM(7, 128, batch_first=True)
            self.sensor_fc = nn.Linear(128, 64)
            self.head = nn.Sequential(nn.Linear(192, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 1))
        def forward(self, sat, sensor):
            x = self.conv(sat)
            x = self.attention(x)
            sat_feat = self.sat_fc(x)
            _, (h, _) = self.lstm(sensor)
            sensor_feat = self.sensor_fc(h[-1])
            return self.head(torch.cat((sat_feat, sensor_feat), dim=1))
    return Model()


class ResidualBlock(nn.Module):
    """R3 用的残差块"""
    def __init__(self, channels):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(channels, channels, 3, padding=1),
            nn.BatchNorm2d(channels),
            nn.ReLU(),
            nn.Conv2d(channels, channels, 3, padding=1),
            nn.BatchNorm2d(channels),
        )
        self.relu = nn.ReLU()
    def forward(self, x):
        return self.relu(self.block(x) + x)


def make_r3():
    """R3: ResidualBlock + Spatial Attention（原用 128×128，此处用 32×32 patch）"""
    class Model(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv2d(1, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
                ResidualBlock(32),
                nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(), nn.MaxPool2d(2),
                ResidualBlock(64),
            )
            self.attention = SpatialAttention(64)
            self.sat_fc = nn.Linear(64, 128)
            self.lstm = nn.LSTM(7, 128, batch_first=True)
            self.sensor_fc = nn.Linear(128, 64)
            self.head = nn.Sequential(nn.Linear(192, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 1))
        def forward(self, sat, sensor):
            x = self.conv(sat)
            x = self.attention(x)
            sat_feat = self.sat_fc(x)
            _, (h, _) = self.lstm(sensor)
            sensor_feat = self.sensor_fc(h[-1])
            return self.head(torch.cat((sat_feat, sensor_feat), dim=1))
    return Model()


def make_r4():
    """R4: 3层 CNN + Spatial Attention，32×32 patch + coord(2)"""
    class Model(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv2d(1, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
            )
            self.attention = SpatialAttention(64)
            self.sat_fc = nn.Linear(64, 128)
            self.lstm = nn.LSTM(7, 128, batch_first=True)
            self.sensor_fc = nn.Linear(128, 64)
            self.head = nn.Sequential(nn.Linear(194, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, 1))
        def forward(self, sat, sensor, coord):
            x = self.conv(sat)
            x = self.attention(x)
            sat_feat = self.sat_fc(x)
            _, (h, _) = self.lstm(sensor)
            sensor_feat = self.sensor_fc(h[-1])
            return self.head(torch.cat((sat_feat, sensor_feat, coord), dim=1))
    return Model()


# =====================================================================
# 训练 + 评估
# =====================================================================

def train_and_eval(model, train_loader, val_loader, use_coord=False):
    """训练模型并返回评估指标。"""
    device = torch.device("cpu")
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    criterion = nn.MSELoss()
    best_val_loss = float("inf")
    best_state = None
    start = time.time()

    for epoch in range(1, EPOCHS + 1):
        model.train()
        for batch in train_loader:
            if use_coord:
                sat, sensor, coord, target = batch
                sat, sensor, coord, target = sat.to(device), sensor.to(device), coord.to(device), target.to(device)
                output = model(sat, sensor, coord)
            else:
                # 兼容旧 3 元组：从 4 元组中忽略 coord，用全图
                sat, sensor, coord, target = batch
                sat, sensor, target = sat.to(device), sensor.to(device), target.to(device)
                output = model(sat, sensor)
            optimizer.zero_grad()
            loss = criterion(output, target)
            loss.backward()
            optimizer.step()

        model.eval()
        val_loss_sum, val_count = 0.0, 0
        with torch.no_grad():
            for batch in val_loader:
                if use_coord:
                    sat, sensor, coord, target = batch
                    sat, sensor, coord, target = sat.to(device), sensor.to(device), coord.to(device), target.to(device)
                    output = model(sat, sensor, coord)
                else:
                    sat, sensor, coord, target = batch
                    sat, sensor, target = sat.to(device), sensor.to(device), target.to(device)
                    output = model(sat, sensor)
                val_loss_sum += criterion(output, target).item() * sat.size(0)
                val_count += sat.size(0)

        val_loss = val_loss_sum / max(val_count, 1)
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

    elapsed = time.time() - start

    # 加载最佳权重评估
    model.load_state_dict(best_state)
    model.eval()
    preds, actuals = [], []
    with torch.no_grad():
        for batch in val_loader:
            if use_coord:
                sat, sensor, coord, target = batch
                sat, sensor, coord = sat.to(device), sensor.to(device), coord.to(device)
                output = model(sat, sensor, coord)
            else:
                sat, sensor, coord, target = batch
                sat, sensor = sat.to(device), sensor.to(device)
                output = model(sat, sensor)
            preds.extend(torch.clamp(output, min=0.0).cpu().numpy().flatten())
            actuals.extend(target.numpy().flatten())

    preds = np.array(preds)
    actuals = np.array(actuals)

    # 计算指标
    mae = np.mean(np.abs(preds - actuals))
    rmse = np.sqrt(np.mean((preds - actuals) ** 2))
    pred_rain = preds > RAIN_THRESHOLD
    true_rain = actuals > RAIN_THRESHOLD
    tp = int((pred_rain & true_rain).sum())
    fp = int((pred_rain & ~true_rain).sum())
    fn = int((~pred_rain & true_rain).sum())
    tn = int((~pred_rain & ~true_rain).sum())
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    params = sum(p.numel() for p in model.parameters())

    return {
        'val_loss': best_val_loss, 'mae': mae, 'rmse': rmse,
        'precision': prec, 'recall': rec, 'f1': f1,
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'time': elapsed, 'params': params
    }


def main():
    logger.info("=" * 60)
    logger.info(f"全轮次对比 | 阈值={RAIN_THRESHOLD}mm | {EPOCHS} epochs")
    logger.info("⚠️  注意：所有模型均使用 32×32 patch 输入（dataset 已改为局部裁剪）")
    logger.info("=" * 60)

    train_loader, val_loader = get_dataloaders(
        "real_sensor_data.csv", "satellite_data", batch_size=BATCH_SIZE
    )

    configs = [
        ("Baseline (GAP)", make_baseline, False),
        ("R1: +Attention", make_r1, False),
        ("R2: +DeepCNN", make_r2, False),
        ("R3: +Residual", make_r3, False),
        ("R4: Patch+Coord", make_r4, True),
    ]

    results = {}
    for name, factory, use_coord in configs:
        logger.info(f"\n--- {name} ---")
        model = factory()
        logger.info(f"   参数量: {sum(p.numel() for p in model.parameters()):,}")
        r = train_and_eval(model, train_loader, val_loader, use_coord=use_coord)
        results[name] = r
        logger.info(
            f"   Val Loss: {r['val_loss']:.5f} | MAE: {r['mae']:.4f} | "
            f"Prec: {r['precision']*100:.1f}% | Rec: {r['recall']*100:.1f}% | F1: {r['f1']*100:.1f}% | "
            f"TP={r['tp']} FP={r['fp']} FN={r['fn']} TN={r['tn']} | {r['time']:.0f}s"
        )

    # 结果表
    print("\n" + "=" * 80)
    print(f"全轮次对比（阈值 = {RAIN_THRESHOLD}mm）")
    print("=" * 80)
    header = f"{'模型':<20s} {'Val Loss':>9s} {'MAE':>7s} {'Prec':>7s} {'Recall':>7s} {'F1':>7s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'TN':>4s} {'Time':>6s}"
    print(header)
    print("-" * len(header))
    for name, r in results.items():
        print(
            f"{name:<20s} {r['val_loss']:9.5f} {r['mae']:7.4f} "
            f"{r['precision']*100:6.1f}% {r['recall']*100:6.1f}% {r['f1']*100:6.1f}% "
            f"{r['tp']:4d} {r['fp']:4d} {r['fn']:4d} {r['tn']:4d} {r['time']:5.0f}s"
        )


if __name__ == "__main__":
    main()
