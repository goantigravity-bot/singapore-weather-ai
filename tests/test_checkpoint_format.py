"""
Tests for checkpoint save/load format changes.

The temporal satellite feature changes the checkpoint from a plain state_dict
to a dict with {'model_state_dict': ..., 'num_sat_frames': ...}. These tests
verify backward compatibility with old checkpoints and correct metadata
in new checkpoints.
"""
import os
import pytest
import torch
from weather_fusion_model import WeatherFusionNet


class TestCheckpointSaveFormat:
    """Verify new checkpoint format includes metadata."""

    def test_new_checkpoint_has_metadata(self, tmp_model_dir):
        """New-format checkpoint should contain model_state_dict and num_sat_frames."""
        model = WeatherFusionNet(num_sat_frames=6)
        path = os.path.join(tmp_model_dir, "model.pth")

        torch.save({
            'model_state_dict': model.state_dict(),
            'num_sat_frames': 6,
        }, path)

        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        assert isinstance(checkpoint, dict)
        assert 'model_state_dict' in checkpoint
        assert 'num_sat_frames' in checkpoint
        assert checkpoint['num_sat_frames'] == 6

    def test_state_dict_keys_match(self, tmp_model_dir):
        """Saved state_dict keys should match a fresh model's keys."""
        model = WeatherFusionNet(num_sat_frames=6)
        path = os.path.join(tmp_model_dir, "model.pth")

        torch.save({
            'model_state_dict': model.state_dict(),
            'num_sat_frames': 6,
        }, path)

        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        fresh_model = WeatherFusionNet(num_sat_frames=6)
        fresh_model.load_state_dict(checkpoint['model_state_dict'])


class TestCheckpointBackwardCompat:
    """Verify loading old-format checkpoints (plain state_dict) still works."""

    def test_load_old_format_single_frame(self, tmp_model_dir):
        """Old checkpoint (plain state_dict, no metadata) should load as num_sat_frames=1."""
        model = WeatherFusionNet(num_sat_frames=1)
        path = os.path.join(tmp_model_dir, "old_model.pth")

        torch.save(model.state_dict(), path)

        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            num_sat_frames = checkpoint.get('num_sat_frames', 1)
            state_dict = checkpoint['model_state_dict']
        else:
            num_sat_frames = 1
            state_dict = checkpoint

        assert num_sat_frames == 1

        loaded_model = WeatherFusionNet(num_sat_frames=1)
        loaded_model.load_state_dict(state_dict)

    def test_load_new_format_multi_frame(self, tmp_model_dir):
        """New checkpoint with num_sat_frames=6 should be detected correctly."""
        model = WeatherFusionNet(num_sat_frames=6)
        path = os.path.join(tmp_model_dir, "new_model.pth")

        torch.save({
            'model_state_dict': model.state_dict(),
            'num_sat_frames': 6,
        }, path)

        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            num_sat_frames = checkpoint.get('num_sat_frames', 1)
            state_dict = checkpoint['model_state_dict']
        else:
            num_sat_frames = 1
            state_dict = checkpoint

        assert num_sat_frames == 6

        loaded_model = WeatherFusionNet(num_sat_frames=6)
        loaded_model.load_state_dict(state_dict)

    def test_roundtrip_preserves_weights(self, tmp_model_dir):
        """Save and reload should produce identical model outputs."""
        torch.manual_seed(42)
        model = WeatherFusionNet(num_sat_frames=6)
        model.eval()
        path = os.path.join(tmp_model_dir, "roundtrip.pth")

        sat = torch.randn(1, 6, 3, 41, 37)
        sensor = torch.randn(1, 6, 13)
        coord = torch.rand(1, 2)

        with torch.no_grad():
            original_output = model(sat, sensor, coord)

        torch.save({
            'model_state_dict': model.state_dict(),
            'num_sat_frames': 6,
        }, path)

        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        loaded_model = WeatherFusionNet(num_sat_frames=checkpoint['num_sat_frames'])
        loaded_model.load_state_dict(checkpoint['model_state_dict'])
        loaded_model.eval()

        with torch.no_grad():
            loaded_output = loaded_model(sat, sensor, coord)

        assert torch.allclose(original_output, loaded_output, atol=1e-6)

    def test_mismatched_frames_fails(self, tmp_model_dir):
        """Loading a 6-frame checkpoint into a 1-frame model should fail."""
        model = WeatherFusionNet(num_sat_frames=6)
        path = os.path.join(tmp_model_dir, "mismatch.pth")

        torch.save({
            'model_state_dict': model.state_dict(),
            'num_sat_frames': 6,
        }, path)

        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        wrong_model = WeatherFusionNet(num_sat_frames=1)

        with pytest.raises(RuntimeError):
            wrong_model.load_state_dict(checkpoint['model_state_dict'])
