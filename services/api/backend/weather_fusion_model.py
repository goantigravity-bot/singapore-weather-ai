import torch
import torch.nn as nn

class SatelliteEncoder(nn.Module):
    """
    Encoder for Satellite Images (Spatial Data).
    Input: (Batch, Channels, Height, Width)
    Output: (Batch, Feature_Dim)
    """
    def __init__(self, in_channels=3, feature_dim=128):
        super(SatelliteEncoder, self).__init__()
        # Simple CNN backbone (like a mini-ResNet)
        self.conv = nn.Sequential(
            nn.Conv2d(in_channels, 16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(),
            nn.MaxPool2d(2), # H/2, W/2
            
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2), # H/4, W/4
            
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d((1, 1)) # Global Average Pooling -> (Batch, 64, 1, 1)
        )
        self.fc = nn.Linear(64, feature_dim)

    def forward(self, x):
        x = self.conv(x)
        x = x.view(x.size(0), -1) # Flatten
        return self.fc(x)

class SensorEncoder(nn.Module):
    """
    Encoder for Ground Sensor Data (Time-Series Data).
    Input: (Batch, Seq_Len, Features)
    Output: (Batch, Feature_Dim)
    """
    def __init__(self, input_size=5, hidden_size=64, feature_dim=64):
        super(SensorEncoder, self).__init__()
        # LSTM to overlook time dependencies
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
    """
    def __init__(self, sat_channels=3, sensor_features=5, prediction_dim=1):
        super(WeatherFusionNet, self).__init__()
        
        self.sat_encoder = SatelliteEncoder(in_channels=sat_channels, feature_dim=128)
        self.sensor_encoder = SensorEncoder(input_size=sensor_features, feature_dim=64)
        
        # Fusion Layer
        fusion_input_dim = 128 + 64
        self.fusion_head = nn.Sequential(
            nn.Linear(fusion_input_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, prediction_dim) # e.g., predict rainfall amount (regression)
        )

    def forward(self, sat_img, sensor_data):
        """
        sat_img: (Batch, C, H, W)
        sensor_data: (Batch, Seq_Len, F)
        """
        sat_feat = self.sat_encoder(sat_img)
        sensor_feat = self.sensor_encoder(sensor_data)
        
        # Concatenate features
        combined = torch.cat((sat_feat, sensor_feat), dim=1)
        
        output = self.fusion_head(combined)
        return output

# --- Example Usage ---
if __name__ == "__main__":
    # Simulate dummy data
    BATCH_SIZE = 4
    
    # 1. Satellite Data: 4 images, 3 channels (RGB/IR), 64x64 pixels
    dummy_sat_img = torch.randn(BATCH_SIZE, 3, 64, 64)
    
    # 2. Sensor Data: 4 sequences, past 10 timesteps, 5 features (Temp, Humidity, Pressure, WindSpd, WindDir)
    dummy_sensor_data = torch.randn(BATCH_SIZE, 10, 5)
    
    # Initialize Model
    model = WeatherFusionNet(sat_channels=3, sensor_features=5, prediction_dim=1)
    
    # Forward Pass
    prediction = model(dummy_sat_img, dummy_sensor_data)
    
    print(f"Input Satellite Shape: {dummy_sat_img.shape}")
    print(f"Input Sensor Shape:    {dummy_sensor_data.shape}")
    print(f"Output Prediction:     {prediction.shape}")
    print(f"Result: \n{prediction.detach().numpy()}")
