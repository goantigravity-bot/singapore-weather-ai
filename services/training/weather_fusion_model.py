import torch
import torch.nn as nn

class SpatialAttention(nn.Module):
    """
    空间注意力：学习每个位置的重要性权重。
    对云图来说，让模型聚焦在有云的区域，忽略晴空区域。
    """
    def __init__(self, in_channels):
        super(SpatialAttention, self).__init__()
        # 1x1 conv 生成单通道注意力图
        self.attn = nn.Sequential(
            nn.Conv2d(in_channels, 1, kernel_size=1),
            nn.Sigmoid()  # 输出 0~1 的权重
        )

    def forward(self, x):
        # x: (B, C, H, W)
        w = self.attn(x)           # (B, 1, H, W) 注意力权重
        x = x * w                  # 加权
        return x.mean(dim=[2, 3])  # 加权平均池化 → (B, C)


class SatelliteEncoder(nn.Module):
    """
    Encoder for Satellite Images (Spatial Data).
    方案 A: 输入为基站局部 32×32 patch + Spatial Attention
    """
    def __init__(self, in_channels=1, feature_dim=128):
        super(SatelliteEncoder, self).__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_channels, 16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(),
            nn.MaxPool2d(2),  # 32→16

            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2),  # 16→8

            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
        )
        self.attention = SpatialAttention(64)
        self.fc = nn.Linear(64, feature_dim)

    def forward(self, x):
        x = self.conv(x)
        x = self.attention(x)  # (B, 64) — 注意力加权池化
        return self.fc(x)

class SensorEncoder(nn.Module):
    """
    Encoder for Ground Sensor Data (Time-Series Data).
    Input: (Batch, Seq_Len, Features)
    Output: (Batch, Feature_Dim)
    """
    def __init__(self, input_size=7, hidden_size=128, feature_dim=64):
        super(SensorEncoder, self).__init__()
        # LSTM to capture time dependencies in sensor sequences
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, feature_dim)

    def forward(self, x):
        # x: (Batch, Seq_Len, Features)
        # out: (Batch, Seq_Len, Hidden_Size)
        # h_n: (1, Batch, Hidden_Size) - Last hidden state
        _, (h_n, _) = self.lstm(x)
        return self.fc(h_n[-1])

class WeatherFusionNet(nn.Module):
    """
    Fusion Network combining Satellite and Sensor data.
    方案 A: 增加 2 维基站坐标特征到融合层。
    """
    def __init__(self, sat_channels=1, sensor_features=7, coord_dim=2, prediction_dim=1):
        super(WeatherFusionNet, self).__init__()
        
        self.sat_encoder = SatelliteEncoder(in_channels=sat_channels, feature_dim=128)
        self.sensor_encoder = SensorEncoder(input_size=sensor_features, feature_dim=64)
        
        # 融合层: sat(128) + sensor(64) + coord(2) = 194
        fusion_input_dim = 128 + 64 + coord_dim
        self.fusion_head = nn.Sequential(
            nn.Linear(fusion_input_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, prediction_dim)
        )

    def forward(self, sat_img, sensor_data, coord):
        """
        sat_img: (Batch, C, 32, 32) — 基站局部 patch
        sensor_data: (Batch, Seq_Len, F)
        coord: (Batch, 2) — 归一化基站坐标
        """
        sat_feat = self.sat_encoder(sat_img)
        sensor_feat = self.sensor_encoder(sensor_data)
        
        # 拼接: 卫星特征 + 传感器特征 + 基站坐标
        combined = torch.cat((sat_feat, sensor_feat, coord), dim=1)
        
        output = self.fusion_head(combined)
        return output

# --- Example Usage ---
if __name__ == "__main__":
    # Simulate dummy data
    BATCH_SIZE = 4
    
    # 1. Satellite Data: 4 images, 1 channel (IR), 32x32 patch
    dummy_sat_img = torch.randn(BATCH_SIZE, 1, 32, 32)
    
    # 2. Sensor Data: 7 features
    dummy_sensor_data = torch.randn(BATCH_SIZE, 10, 7)
    
    # 3. Coord: normalized station position
    dummy_coord = torch.rand(BATCH_SIZE, 2)
    
    # Initialize Model
    model = WeatherFusionNet(sat_channels=1, sensor_features=7, prediction_dim=1)
    
    # Forward Pass
    prediction = model(dummy_sat_img, dummy_sensor_data, dummy_coord)
    
    print(f"Input Satellite Shape: {dummy_sat_img.shape}")
    print(f"Input Sensor Shape:    {dummy_sensor_data.shape}")
    print(f"Input Coord Shape:     {dummy_coord.shape}")
    print(f"Output Prediction:     {prediction.shape}")
    print(f"Result: \n{prediction.detach().numpy()}")

