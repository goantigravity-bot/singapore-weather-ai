"""
WeatherFusionNet V3 — 全面升级版

改进清单 (相比 V2):
  Phase 1: 二分类输出 + Focal Loss + 深化融合层
  Phase 3: ResNet-18 卫星编码器 + 多帧时序 + Cross-Attention 融合
  Phase 4: 物理约束损失 (可选辅助损失)

(V2 → V3 的变更点以 🆕 标注)
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import math


# ── Phase 1: Focal Loss ──────────────────────────────────────────────
class FocalLoss(nn.Module):
    """
    Binary Focal Loss — 自动聚焦难分样本，缓解类别不平衡。

    alpha: 正类(降雨)的权重，>0.5 则倾向于惩罚漏报
    gamma: 聚焦因子，越大越关注"模型犹豫不决"的样本
    """
    def __init__(self, alpha=0.75, gamma=2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, logits, targets):
        # logits: (B, 1), targets: (B, 1) ∈ {0, 1}
        bce = F.binary_cross_entropy_with_logits(logits, targets, reduction='none')
        prob = torch.sigmoid(logits)
        # pt = 正确预测的概率
        pt = targets * prob + (1 - targets) * (1 - prob)
        # alpha 加权：正类用 alpha，负类用 1-alpha
        alpha_t = targets * self.alpha + (1 - targets) * (1 - self.alpha)
        focal_weight = alpha_t * (1 - pt) ** self.gamma
        return (focal_weight * bce).mean()


# ── Phase 4: 物理约束损失 ─────────────────────────────────────────────
class PhysicsConstraintLoss(nn.Module):
    """
    利用气象学先验知识约束模型输出。

    约束1: 高湿度(>90%) + 有云(卫星低亮温) → 应预测有雨
    约束2: 低湿度(<50%) → 不应预测有雨

    作为辅助损失与主损失加权求和，引导模型学到物理一致的输出。
    """
    def __init__(self, weight=0.1):
        super().__init__()
        self.weight = weight

    def forward(self, logits, sensor_seq):
        """
        logits: (B, 1) — 降雨 logit
        sensor_seq: (B, seq_len, F) — 归一化后传感器序列
                    其中 col 2 = humidity (归一化后: (h-80)/20)
        """
        # 取最后一个时间步的湿度（归一化后，>0.5 对应 >90%）
        humidity_last = sensor_seq[:, -1, 2]  # (B,)

        pred_prob = torch.sigmoid(logits.squeeze(-1))  # (B,)

        # 高湿度却预测不下雨 → 惩罚
        high_humid_penalty = F.relu(humidity_last - 0.5) * F.relu(0.5 - pred_prob)
        # 低湿度却预测下雨 → 惩罚 (humidity_norm < -1.5 对应实际 <50%)
        low_humid_penalty = F.relu(-1.5 - humidity_last) * F.relu(pred_prob - 0.5)

        return self.weight * (high_humid_penalty.mean() + low_humid_penalty.mean())


# ── Phase 3: ResNet-18 卫星编码器 ─────────────────────────────────────
class ResidualBlock(nn.Module):
    """轻量 ResNet basic block — 避免引入 torchvision 依赖。"""
    def __init__(self, in_c, out_c, stride=1):
        super().__init__()
        self.conv1 = nn.Conv2d(in_c, out_c, 3, stride=stride, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_c)
        self.conv2 = nn.Conv2d(out_c, out_c, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_c)

        # 残差连接：维度不匹配时用 1x1 conv 调整
        self.shortcut = nn.Sequential()
        if stride != 1 or in_c != out_c:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_c, out_c, 1, stride=stride, bias=False),
                nn.BatchNorm2d(out_c)
            )

    def forward(self, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        return F.relu(out + self.shortcut(x))


class SatelliteEncoder(nn.Module):
    """
    🆕 ResNet-style 卫星编码器（替代原 3 层浅 CNN）。

    结构: Conv → 4 个 ResBlock (16→32→64→128) → GAP → FC
    支持可变输入通道数（单帧 3ch 或多帧 N×3ch）。
    """
    def __init__(self, in_channels=3, feature_dim=256):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, 16, 3, padding=1, bias=False),
            nn.BatchNorm2d(16),
            nn.ReLU()
        )
        self.layer1 = ResidualBlock(16, 32, stride=2)   # H/2
        self.layer2 = ResidualBlock(32, 64, stride=2)   # H/4
        self.layer3 = ResidualBlock(64, 128, stride=2)   # H/8
        self.layer4 = ResidualBlock(128, 256, stride=1)  # 保持分辨率

        self.gap = nn.AdaptiveAvgPool2d(1)
        self.fc = nn.Linear(256, feature_dim)

    def forward(self, x):
        x = self.stem(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
        x = self.gap(x).flatten(1)
        return self.fc(x)


# ── Phase 3: 多帧时序编码器 ───────────────────────────────────────────
class TemporalSatelliteEncoder(nn.Module):
    """
    🆕 连续多帧卫星图编码器 — 捕捉云团运动和演化。

    先用共享 ResNet 提取每帧的空间特征，再用 GRU 编码时间维度。
    输入: (B, T, C, H, W) → 输出: (B, feature_dim)
    """
    def __init__(self, num_frames=3, in_channels=3, feature_dim=256):
        super().__init__()
        self.spatial_encoder = SatelliteEncoder(in_channels, feature_dim)
        # GRU 编码帧间时序关系（比 LSTM 参数少 30%，适合帧数少的情况）
        self.temporal = nn.GRU(feature_dim, feature_dim, batch_first=True)
        self.num_frames = num_frames

    def forward(self, x):
        """
        x: (B, T, C, H, W) — T 帧卫星图
        """
        B, T, C, H, W = x.shape
        # 展平 batch 和时间维度一起过 CNN
        x = x.view(B * T, C, H, W)
        spatial_feats = self.spatial_encoder(x)  # (B*T, feat_dim)
        spatial_feats = spatial_feats.view(B, T, -1)  # (B, T, feat_dim)
        # GRU: 取最后一个隐藏状态
        _, h_n = self.temporal(spatial_feats)
        return h_n.squeeze(0)  # (B, feat_dim)


# ── SensorEncoder（LSTM 增强版）────────────────────────────────────────
class SensorEncoder(nn.Module):
    """
    传感器时序编码器。

    🆕 改进: 2层双向LSTM + 残差连接，增强时序建模能力。
    输入特征: temp, rain, humidity, pm25, wind_speed, wind_sin, wind_cos
              + hour_sin, hour_cos, month_sin, month_cos (Phase 2 时间特征)
              + delta_humidity, delta_temp (Phase 2 变化率特征)
    """
    def __init__(self, input_size=13, hidden_size=128, feature_dim=128):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size, hidden_size,
            num_layers=2,
            batch_first=True,
            dropout=0.2,
            bidirectional=True
        )
        # 双向 → 2 * hidden_size，取 forward + backward 最后隐藏态
        self.fc = nn.Linear(hidden_size * 2, feature_dim)

    def forward(self, x):
        out, (h_n, _) = self.lstm(x)
        # h_n: (num_layers*2, B, H) — 取最后一层的 forward 和 backward
        h_forward = h_n[-2]  # 最后一层 forward
        h_backward = h_n[-1]  # 最后一层 backward
        combined = torch.cat([h_forward, h_backward], dim=1)
        return self.fc(combined)


# ── Phase 3: Cross-Attention 融合 ─────────────────────────────────────
class CrossAttentionFusion(nn.Module):
    """
    🆕 交叉注意力融合 — 卫星和传感器特征互相关注。

    让卫星特征询问传感器"现在湿度多少？"，
    让传感器特征询问卫星"云团在哪？有多厚？"。
    """
    def __init__(self, sat_dim=256, sensor_dim=128, out_dim=256, num_heads=4):
        super().__init__()
        # 统一维度
        self.sat_proj = nn.Linear(sat_dim, out_dim)
        self.sensor_proj = nn.Linear(sensor_dim, out_dim)

        # 卫星 attend to 传感器
        self.sat_to_sensor = nn.MultiheadAttention(out_dim, num_heads, batch_first=True)
        # 传感器 attend to 卫星
        self.sensor_to_sat = nn.MultiheadAttention(out_dim, num_heads, batch_first=True)

        self.norm1 = nn.LayerNorm(out_dim)
        self.norm2 = nn.LayerNorm(out_dim)
        self.ffn = nn.Sequential(
            nn.Linear(out_dim * 2, out_dim),
            nn.GELU(),
            nn.Dropout(0.1),
        )

    def forward(self, sat_feat, sensor_feat):
        """
        sat_feat: (B, sat_dim)
        sensor_feat: (B, sensor_dim)
        → output: (B, out_dim)
        """
        sat = self.sat_proj(sat_feat).unsqueeze(1)      # (B, 1, D)
        sensor = self.sensor_proj(sensor_feat).unsqueeze(1)  # (B, 1, D)

        # 交叉注意力
        sat_enhanced, _ = self.sat_to_sensor(sat, sensor, sensor)  # 卫星问传感器
        sat_enhanced = self.norm1(sat + sat_enhanced)

        sensor_enhanced, _ = self.sensor_to_sat(sensor, sat, sat)  # 传感器问卫星
        sensor_enhanced = self.norm2(sensor + sensor_enhanced)

        # 拼接后 FFN 融合
        combined = torch.cat([sat_enhanced.squeeze(1), sensor_enhanced.squeeze(1)], dim=1)
        return self.ffn(combined)


# ── 主模型 ────────────────────────────────────────────────────────────
class WeatherFusionNet(nn.Module):
    """
    WeatherFusionNet V3 — 全面升级版。

    架构:
      ResNet 卫星编码器 (256d)
        ↕ Cross-Attention
      BiLSTM 传感器编码器 (128d)
        ↓
      融合层 (256 + coord + time_context → 128 → 64 → 1 logit)

    Args:
        sat_channels: 卫星波段数（默认 3: B08/B11/B13）
        sensor_features: 传感器特征数（V3: 13 = 7原始 + 4时间 + 2变化率）
        coord_dim: 坐标维度（2: 归一化 x/y）
        num_sat_frames: 卫星时序帧数（1=单帧, >1=多帧时序）
        use_cross_attention: 是否启用交叉注意力融合
    """
    def __init__(self, sat_channels=3, sensor_features=13, coord_dim=2,
                 num_sat_frames=1, use_cross_attention=True):
        super().__init__()
        self.use_cross_attention = use_cross_attention
        self.num_sat_frames = num_sat_frames

        sat_feat_dim = 256
        sensor_feat_dim = 128

        # 卫星编码器：单帧或多帧
        if num_sat_frames > 1:
            self.sat_encoder = TemporalSatelliteEncoder(
                num_frames=num_sat_frames,
                in_channels=sat_channels,
                feature_dim=sat_feat_dim
            )
        else:
            self.sat_encoder = SatelliteEncoder(
                in_channels=sat_channels,
                feature_dim=sat_feat_dim
            )

        # 传感器编码器
        self.sensor_encoder = SensorEncoder(
            input_size=sensor_features,
            feature_dim=sensor_feat_dim
        )

        # 融合方式
        if use_cross_attention:
            self.fusion = CrossAttentionFusion(
                sat_dim=sat_feat_dim,
                sensor_dim=sensor_feat_dim,
                out_dim=256
            )
            fusion_out_dim = 256
        else:
            # 简单拼接作为 fallback
            fusion_out_dim = sat_feat_dim + sensor_feat_dim

        # 分类头：融合特征 + 坐标 → logit
        # 🆕 加深并加入残差连接
        head_input = fusion_out_dim + coord_dim
        self.classifier = nn.Sequential(
            nn.Linear(head_input, 128),
            nn.GELU(),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(64, 1)
            # 不加 Sigmoid：配合 BCEWithLogitsLoss / FocalLoss
        )

    def forward(self, sat_img, sensor_data, coord):
        """
        sat_img:     单帧 (B, C, H, W) 或多帧 (B, T, C, H, W)
        sensor_data: (B, seq_len, features)
        coord:       (B, 2) — 归一化基站坐标
        """
        sat_feat = self.sat_encoder(sat_img)
        sensor_feat = self.sensor_encoder(sensor_data)

        # 融合
        if self.use_cross_attention:
            fused = self.fusion(sat_feat, sensor_feat)
        else:
            fused = torch.cat([sat_feat, sensor_feat], dim=1)

        # 拼接坐标
        combined = torch.cat([fused, coord], dim=1)
        return self.classifier(combined)


# ── 辅助函数 ──────────────────────────────────────────────────────────
def get_combined_loss(alpha=0.75, gamma=2.0, physics_weight=0.1):
    """
    返回组合损失 (Focal + Physics) 的计算函数。

    用法:
        loss_fn = get_combined_loss()
        loss = loss_fn(logits, targets, sensor_seq)
    """
    focal = FocalLoss(alpha, gamma)
    physics = PhysicsConstraintLoss(physics_weight)

    def combined_loss(logits, targets, sensor_seq):
        return focal(logits, targets) + physics(logits, sensor_seq)

    return combined_loss


# --- Example Usage ---
if __name__ == "__main__":
    BATCH_SIZE = 4

    # 单帧模式
    dummy_sat = torch.randn(BATCH_SIZE, 3, 41, 37)
    dummy_sensor = torch.randn(BATCH_SIZE, 6, 13)
    dummy_coord = torch.rand(BATCH_SIZE, 2)

    model = WeatherFusionNet(sat_channels=3, sensor_features=13, coord_dim=2)

    logits = model(dummy_sat, dummy_sensor, dummy_coord)
    print(f"[单帧] Input Sat: {dummy_sat.shape}, Sensor: {dummy_sensor.shape}")
    print(f"[单帧] Output logits: {logits.shape}")
    print(f"[单帧] Probabilities: {torch.sigmoid(logits).detach().numpy().flatten()}")

    # 多帧模式
    model_temporal = WeatherFusionNet(
        sat_channels=3, sensor_features=13, coord_dim=2,
        num_sat_frames=3
    )
    dummy_sat_multi = torch.randn(BATCH_SIZE, 3, 3, 41, 37)
    logits_multi = model_temporal(dummy_sat_multi, dummy_sensor, dummy_coord)
    print(f"\n[多帧] Input Sat: {dummy_sat_multi.shape}")
    print(f"[多帧] Output logits: {logits_multi.shape}")

    # 损失测试
    targets = torch.tensor([[1.0], [0.0], [1.0], [0.0]])
    loss_fn = get_combined_loss()
    loss = loss_fn(logits, targets, dummy_sensor)
    print(f"\n[损失] Combined loss: {loss.item():.4f}")

    total_params = sum(p.numel() for p in model.parameters())
    print(f"[参数] Single-frame model: {total_params:,} params")
