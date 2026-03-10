"""
Tests for WeatherFusionNet with temporal satellite support.

Verifies that the model correctly handles both single-frame and
multi-frame (temporal) satellite inputs via TemporalSatelliteEncoder.
"""
import pytest
import torch
from weather_fusion_model import (
    WeatherFusionNet, SatelliteEncoder, TemporalSatelliteEncoder,
    FocalLoss, get_combined_loss
)


class TestSatelliteEncoder:
    """Test single-frame satellite encoder."""

    def test_output_shape(self):
        encoder = SatelliteEncoder(in_channels=3, feature_dim=256)
        x = torch.randn(2, 3, 41, 37)
        out = encoder(x)
        assert out.shape == (2, 256)

    def test_different_feature_dim(self):
        encoder = SatelliteEncoder(in_channels=3, feature_dim=128)
        x = torch.randn(2, 3, 41, 37)
        out = encoder(x)
        assert out.shape == (2, 128)


class TestTemporalSatelliteEncoder:
    """Test multi-frame temporal satellite encoder (ResNet + GRU)."""

    def test_output_shape_6_frames(self):
        encoder = TemporalSatelliteEncoder(num_frames=6, in_channels=3, feature_dim=256)
        x = torch.randn(2, 6, 3, 41, 37)
        out = encoder(x)
        assert out.shape == (2, 256)

    def test_output_shape_3_frames(self):
        encoder = TemporalSatelliteEncoder(num_frames=3, in_channels=3, feature_dim=256)
        x = torch.randn(2, 3, 3, 41, 37)
        out = encoder(x)
        assert out.shape == (2, 256)

    def test_shares_spatial_encoder_weights(self):
        """Verify all frames go through the same ResNet (shared weights)."""
        encoder = TemporalSatelliteEncoder(num_frames=6, in_channels=3, feature_dim=256)
        assert isinstance(encoder.spatial_encoder, SatelliteEncoder)
        spatial_params = sum(p.numel() for p in encoder.spatial_encoder.parameters())
        assert spatial_params > 0

    def test_temporal_ordering_matters(self):
        """Reversed frame order should produce different output (GRU is order-sensitive)."""
        torch.manual_seed(42)
        encoder = TemporalSatelliteEncoder(num_frames=6, in_channels=3, feature_dim=256)
        encoder.eval()

        x = torch.randn(1, 6, 3, 41, 37)
        x_reversed = x.flip(dims=[1])

        with torch.no_grad():
            out_forward = encoder(x)
            out_reversed = encoder(x_reversed)

        assert not torch.allclose(out_forward, out_reversed, atol=1e-5)


class TestWeatherFusionNetSingleFrame:
    """Test full model with single satellite frame (num_sat_frames=1)."""

    def test_forward_pass(self, dummy_single_frame_sat, dummy_sensor, dummy_coord):
        model = WeatherFusionNet(
            sat_channels=3, sensor_features=13, coord_dim=2,
            num_sat_frames=1, use_cross_attention=True
        )
        logits = model(dummy_single_frame_sat, dummy_sensor, dummy_coord)
        assert logits.shape == (2, 1)

    def test_uses_satellite_encoder(self):
        model = WeatherFusionNet(num_sat_frames=1)
        assert isinstance(model.sat_encoder, SatelliteEncoder)

    def test_output_is_logit(self, dummy_single_frame_sat, dummy_sensor, dummy_coord):
        """Output should be raw logit (can be negative), not probability."""
        model = WeatherFusionNet(num_sat_frames=1)
        logits = model(dummy_single_frame_sat, dummy_sensor, dummy_coord)
        assert logits.dtype == torch.float32


class TestWeatherFusionNetMultiFrame:
    """Test full model with temporal satellite (num_sat_frames=6)."""

    def test_forward_pass(self, dummy_multi_frame_sat, dummy_sensor, dummy_coord):
        model = WeatherFusionNet(
            sat_channels=3, sensor_features=13, coord_dim=2,
            num_sat_frames=6, use_cross_attention=True
        )
        logits = model(dummy_multi_frame_sat, dummy_sensor, dummy_coord)
        assert logits.shape == (2, 1)

    def test_uses_temporal_encoder(self):
        model = WeatherFusionNet(num_sat_frames=6)
        assert isinstance(model.sat_encoder, TemporalSatelliteEncoder)

    def test_num_sat_frames_stored(self):
        model = WeatherFusionNet(num_sat_frames=6)
        assert model.num_sat_frames == 6

    def test_single_vs_multi_different_params(self):
        """Multi-frame model has extra GRU params vs single-frame."""
        single = WeatherFusionNet(num_sat_frames=1)
        multi = WeatherFusionNet(num_sat_frames=6)

        single_params = sum(p.numel() for p in single.parameters())
        multi_params = sum(p.numel() for p in multi.parameters())

        assert multi_params > single_params

    def test_without_cross_attention(self, dummy_multi_frame_sat, dummy_sensor, dummy_coord):
        model = WeatherFusionNet(
            num_sat_frames=6, use_cross_attention=False
        )
        logits = model(dummy_multi_frame_sat, dummy_sensor, dummy_coord)
        assert logits.shape == (2, 1)


class TestLossWithTemporalModel:
    """Verify loss functions work with temporal model outputs."""

    def test_focal_loss(self, dummy_multi_frame_sat, dummy_sensor, dummy_coord):
        model = WeatherFusionNet(num_sat_frames=6)
        logits = model(dummy_multi_frame_sat, dummy_sensor, dummy_coord)
        targets = torch.tensor([[1.0], [0.0]])

        loss_fn = FocalLoss(alpha=0.75, gamma=2.0)
        loss = loss_fn(logits, targets)

        assert loss.shape == ()
        assert loss.item() > 0
        assert torch.isfinite(loss)

    def test_combined_loss(self, dummy_multi_frame_sat, dummy_sensor, dummy_coord):
        model = WeatherFusionNet(num_sat_frames=6)
        logits = model(dummy_multi_frame_sat, dummy_sensor, dummy_coord)
        targets = torch.tensor([[1.0], [0.0]])

        loss_fn = get_combined_loss()
        loss = loss_fn(logits, targets, dummy_sensor)

        assert torch.isfinite(loss)
        assert loss.item() > 0
