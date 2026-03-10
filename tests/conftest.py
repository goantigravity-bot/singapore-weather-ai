"""
Shared fixtures for temporal satellite feature tests.
"""
import sys
import os
import pytest
import torch
import numpy as np
import tempfile
import shutil

# Add training module to path FIRST (has the V3 model with TemporalSatelliteEncoder)
# API backend has an older copy of weather_fusion_model.py — training version is canonical
TRAINING_DIR = os.path.join(os.path.dirname(__file__), '..', 'services', 'training')
API_BACKEND_DIR = os.path.join(os.path.dirname(__file__), '..', 'services', 'api', 'backend')
sys.path.insert(0, os.path.abspath(API_BACKEND_DIR))
sys.path.insert(0, os.path.abspath(TRAINING_DIR))  # must be first (index 0)


# --- Constants matching training code ---
SAT_HEIGHT = 41
SAT_WIDTH = 37
SAT_CHANNELS = 3
SAT_BANDS = ['B08', 'B11', 'B13']
SENSOR_FEATURES = 13
SEQ_LEN = 6
BATCH_SIZE = 2


@pytest.fixture
def dummy_single_frame_sat():
    """Single satellite frame: (B, C, H, W)"""
    return torch.randn(BATCH_SIZE, SAT_CHANNELS, SAT_HEIGHT, SAT_WIDTH)


@pytest.fixture
def dummy_multi_frame_sat():
    """6-frame temporal satellite: (B, T, C, H, W)"""
    return torch.randn(BATCH_SIZE, 6, SAT_CHANNELS, SAT_HEIGHT, SAT_WIDTH)


@pytest.fixture
def dummy_sensor():
    """Sensor sequence: (B, seq_len, features)"""
    return torch.randn(BATCH_SIZE, SEQ_LEN, SENSOR_FEATURES)


@pytest.fixture
def dummy_coord():
    """Normalized station coordinates: (B, 2)"""
    return torch.rand(BATCH_SIZE, 2)


@pytest.fixture
def tmp_sat_dir():
    """Create a temp directory with synthetic satellite .npy files."""
    tmpdir = tempfile.mkdtemp(prefix="test_sat_")

    # Create 10 timestamps (10-min intervals) of 3-band satellite data
    base_date = "20260310"
    for i in range(10):
        hour = 10 + i // 6
        minute = (i % 6) * 10
        ts = f"{base_date}_{hour:02d}{minute:02d}"
        for band in SAT_BANDS:
            data = np.random.rand(SAT_HEIGHT, SAT_WIDTH).astype(np.float32) * 100 + 200
            np.save(os.path.join(tmpdir, f"SAT_{band}_{ts}.npy"), data)

    yield tmpdir
    shutil.rmtree(tmpdir)


@pytest.fixture
def tmp_model_dir():
    """Temp directory for saving/loading model checkpoints."""
    tmpdir = tempfile.mkdtemp(prefix="test_model_")
    yield tmpdir
    shutil.rmtree(tmpdir)
