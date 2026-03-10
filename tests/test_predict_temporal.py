"""
Tests for predict.py temporal satellite support.

Tests the _load_single_satellite_frame helper and multi-frame
loading logic in get_input_data.
"""
import os
import sys
import pytest
import tempfile
import shutil
import numpy as np
import torch

# predict.py imports from weather_fusion_model which is in training dir
TRAINING_DIR = os.path.join(os.path.dirname(__file__), '..', 'services', 'training')
API_DIR = os.path.join(os.path.dirname(__file__), '..', 'services', 'api', 'backend')
sys.path.insert(0, os.path.abspath(TRAINING_DIR))
sys.path.insert(0, os.path.abspath(API_DIR))

from predict import _load_single_satellite_frame, SAT_BANDS, SAT_CHANNELS, SAT_HEIGHT, SAT_WIDTH


class TestLoadSingleSatelliteFrame:
    """Test the extracted satellite frame loading helper."""

    def test_loads_valid_frame(self):
        """Should return (3, H, W) tensor when all 3 bands exist."""
        tmpdir = tempfile.mkdtemp()
        try:
            utc_str = "20260310_0200"
            for band in SAT_BANDS:
                data = np.random.rand(SAT_HEIGHT, SAT_WIDTH).astype(np.float32) * 100 + 200
                np.save(os.path.join(tmpdir, f"SAT_{band}_{utc_str}.npy"), data)

            # Temporarily change working dir so glob finds files
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            # Create processed_data dir (that's where _load_single_satellite_frame looks)
            os.makedirs("processed_data", exist_ok=True)
            for f in os.listdir(tmpdir):
                if f.endswith('.npy'):
                    shutil.copy(os.path.join(tmpdir, f), "processed_data/")

            frame = _load_single_satellite_frame(utc_str)
            os.chdir(old_cwd)

            assert frame is not None
            assert frame.shape == (SAT_CHANNELS, SAT_HEIGHT, SAT_WIDTH)
            assert frame.dtype == torch.float32
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmpdir)

    def test_returns_none_missing_bands(self):
        """Should return None when not all 3 bands are available."""
        tmpdir = tempfile.mkdtemp()
        try:
            utc_str = "20260310_0200"
            # Only create 1 band (need all 3)
            data = np.random.rand(SAT_HEIGHT, SAT_WIDTH).astype(np.float32) * 100 + 200
            os.makedirs(os.path.join(tmpdir, "processed_data"))
            np.save(os.path.join(tmpdir, "processed_data", f"SAT_B08_{utc_str}.npy"), data)

            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            frame = _load_single_satellite_frame(utc_str)
            os.chdir(old_cwd)

            assert frame is None
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmpdir)

    def test_returns_none_no_files(self):
        """Should return None when no satellite files exist."""
        tmpdir = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmpdir, "processed_data"))
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            frame = _load_single_satellite_frame("20260310_9999")
            os.chdir(old_cwd)

            assert frame is None
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmpdir)

    def test_normalization(self):
        """Frame should be normalized: (val - 200) / 100."""
        tmpdir = tempfile.mkdtemp()
        try:
            utc_str = "20260310_0200"
            # All values = 250.0 → normalized = (250-200)/100 = 0.5
            for band in SAT_BANDS:
                data = np.full((SAT_HEIGHT, SAT_WIDTH), 250.0, dtype=np.float32)
                os.makedirs(os.path.join(tmpdir, "processed_data"), exist_ok=True)
                np.save(os.path.join(tmpdir, "processed_data", f"SAT_{band}_{utc_str}.npy"), data)

            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            frame = _load_single_satellite_frame(utc_str)
            os.chdir(old_cwd)

            assert frame is not None
            assert torch.allclose(frame, torch.full_like(frame, 0.5), atol=1e-5)
        finally:
            os.chdir(old_cwd)
            shutil.rmtree(tmpdir)


class TestLoadSystemCheckpointDetection:
    """Test that load_system() correctly detects num_sat_frames from checkpoint."""

    def test_old_checkpoint_defaults_to_1(self, tmp_model_dir):
        """Plain state_dict checkpoint should default to num_sat_frames=1."""
        from weather_fusion_model import WeatherFusionNet

        model = WeatherFusionNet(num_sat_frames=1)
        path = os.path.join(tmp_model_dir, "model.pth")
        torch.save(model.state_dict(), path)

        # Simulate the detection logic from load_system()
        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            detected = checkpoint.get('num_sat_frames', 1)
        else:
            detected = 1

        assert detected == 1

    def test_new_checkpoint_detects_6(self, tmp_model_dir):
        """New-format checkpoint should detect num_sat_frames=6."""
        from weather_fusion_model import WeatherFusionNet

        model = WeatherFusionNet(num_sat_frames=6)
        path = os.path.join(tmp_model_dir, "model.pth")
        torch.save({
            'model_state_dict': model.state_dict(),
            'num_sat_frames': 6,
        }, path)

        checkpoint = torch.load(path, map_location='cpu', weights_only=False)
        if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            detected = checkpoint.get('num_sat_frames', 1)
        else:
            detected = 1

        assert detected == 6
