"""
Tests for WeatherDataset multi-frame satellite loading.

Uses synthetic CSV + NPY files to verify that num_sat_frames=6
produces (T, C, H, W) tensors and num_sat_frames=1 produces (C, H, W).
"""
import os
import pytest
import tempfile
import shutil
import numpy as np
import pandas as pd
import torch

from weather_dataset import WeatherDataset, get_dataloaders, SAT_BANDS, SAT_HEIGHT, SAT_WIDTH


def _create_test_data(tmpdir, num_timestamps=20):
    """Create minimal CSV + satellite NPY files for testing."""
    sat_dir = os.path.join(tmpdir, "satellite")
    os.makedirs(sat_dir, exist_ok=True)

    # Generate timestamps: 10-min intervals starting 2026-03-10 10:00 SGT
    # Satellite files are in UTC (SGT - 8h = 02:00 UTC)
    base_sgt = pd.Timestamp("2026-03-10 10:00:00")
    timestamps_sgt = [base_sgt + pd.Timedelta(minutes=10 * i) for i in range(num_timestamps)]

    # Create satellite NPY files (in UTC naming)
    for ts_sgt in timestamps_sgt:
        ts_utc = ts_sgt - pd.Timedelta(hours=8)
        utc_str = ts_utc.strftime("%Y%m%d_%H%M")
        for band in SAT_BANDS:
            data = np.random.rand(SAT_HEIGHT, SAT_WIDTH).astype(np.float32) * 100 + 200
            np.save(os.path.join(sat_dir, f"SAT_{band}_{utc_str}.npy"), data)

    # Create sensor CSV with 2 stations
    rows = []
    for sid in ["S50", "S109"]:
        for ts in timestamps_sgt:
            rows.append({
                'timestamp': ts.strftime("%Y-%m-%d %H:%M:%S"),
                'sensor_id': sid,
                'temperature': 28.0 + np.random.randn() * 2,
                'rainfall': max(0, np.random.randn() * 0.5),
                'humidity': 80.0 + np.random.randn() * 10,
                'pm25': 15.0 + np.random.randn() * 5,
                'wind_speed': abs(np.random.randn() * 3),
                'wind_direction': np.random.rand() * 360,
            })

    csv_path = os.path.join(tmpdir, "sensor_data.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False)

    return csv_path, sat_dir


@pytest.fixture
def test_data():
    """Create temp test data, yield paths, then cleanup."""
    tmpdir = tempfile.mkdtemp(prefix="test_dataset_")
    csv_path, sat_dir = _create_test_data(tmpdir, num_timestamps=20)
    yield csv_path, sat_dir
    shutil.rmtree(tmpdir)


class TestDatasetSingleFrame:
    """Test WeatherDataset with num_sat_frames=1 (original behavior)."""

    def test_sat_shape_single_frame(self, test_data):
        csv_path, sat_dir = test_data
        ds = WeatherDataset(csv_path, sat_dir, num_sat_frames=1)

        if len(ds) > 0:
            sat, sensor, coord, target = ds[0]
            assert sat.shape == (3, SAT_HEIGHT, SAT_WIDTH), f"Expected (3, 41, 37), got {sat.shape}"

    def test_sensor_shape(self, test_data):
        csv_path, sat_dir = test_data
        ds = WeatherDataset(csv_path, sat_dir, num_sat_frames=1)

        if len(ds) > 0:
            sat, sensor, coord, target = ds[0]
            assert sensor.shape == (6, 13)

    def test_target_shape(self, test_data):
        csv_path, sat_dir = test_data
        ds = WeatherDataset(csv_path, sat_dir, num_sat_frames=1)

        if len(ds) > 0:
            sat, sensor, coord, target = ds[0]
            assert target.shape == (1,)


class TestDatasetMultiFrame:
    """Test WeatherDataset with num_sat_frames=6."""

    def test_sat_shape_multi_frame(self, test_data):
        csv_path, sat_dir = test_data
        ds = WeatherDataset(csv_path, sat_dir, num_sat_frames=6)

        if len(ds) > 0:
            sat, sensor, coord, target = ds[0]
            # Multi-frame: (T, C, H, W)
            assert sat.shape == (6, 3, SAT_HEIGHT, SAT_WIDTH), f"Expected (6, 3, 41, 37), got {sat.shape}"

    def test_sensor_unchanged(self, test_data):
        """Sensor tensor should be unaffected by num_sat_frames."""
        csv_path, sat_dir = test_data
        ds = WeatherDataset(csv_path, sat_dir, num_sat_frames=6)

        if len(ds) > 0:
            sat, sensor, coord, target = ds[0]
            assert sensor.shape == (6, 13)

    def test_coord_unchanged(self, test_data):
        """Coordinate tensor should be unaffected by num_sat_frames."""
        csv_path, sat_dir = test_data
        ds = WeatherDataset(csv_path, sat_dir, num_sat_frames=6)

        if len(ds) > 0:
            sat, sensor, coord, target = ds[0]
            assert coord.shape == (2,)

    def test_frames_are_normalized(self, test_data):
        """Each satellite frame should be normalized: (val - 200) / 100."""
        csv_path, sat_dir = test_data
        ds = WeatherDataset(csv_path, sat_dir, num_sat_frames=6)

        if len(ds) > 0:
            sat, _, _, _ = ds[0]
            # Raw values are ~200-300, normalized should be ~0-1
            assert sat.min() >= -3.0, "Normalized values seem too low"
            assert sat.max() <= 3.0, "Normalized values seem too high"

    def test_missing_frames_zero_filled(self):
        """When satellite frames are missing, they should be zero-filled."""
        tmpdir = tempfile.mkdtemp(prefix="test_missing_")
        try:
            # Create data with only 3 satellite timestamps (not enough for 6 frames)
            csv_path, sat_dir = _create_test_data(tmpdir, num_timestamps=20)

            # Delete some satellite files to simulate missing frames
            npy_files = sorted([f for f in os.listdir(sat_dir) if f.endswith('.npy')])
            # Keep only first 3 timestamps (9 files = 3 timestamps * 3 bands)
            for f in npy_files[9:]:
                os.remove(os.path.join(sat_dir, f))

            ds = WeatherDataset(csv_path, sat_dir, num_sat_frames=6)
            if len(ds) > 0:
                sat, _, _, _ = ds[0]
                assert sat.shape == (6, 3, SAT_HEIGHT, SAT_WIDTH)
                # Some frames should be all zeros (missing)
                frame_sums = [sat[t].abs().sum().item() for t in range(6)]
                has_zeros = any(s == 0.0 for s in frame_sums)
                assert has_zeros, "Expected some zero-filled frames for missing data"
        finally:
            shutil.rmtree(tmpdir)


class TestGetDataloaders:
    """Test get_dataloaders with num_sat_frames parameter."""

    def test_passes_num_sat_frames(self, test_data):
        csv_path, sat_dir = test_data
        train_loader, val_loader = get_dataloaders(
            csv_path, sat_dir, batch_size=2, num_sat_frames=6
        )

        # Check the underlying dataset has num_sat_frames=6
        dataset = train_loader.dataset
        # Subset wraps the real dataset
        if hasattr(dataset, 'dataset'):
            dataset = dataset.dataset
        assert dataset.num_sat_frames == 6

    def test_default_single_frame(self, test_data):
        csv_path, sat_dir = test_data
        train_loader, val_loader = get_dataloaders(
            csv_path, sat_dir, batch_size=2
        )

        dataset = train_loader.dataset
        if hasattr(dataset, 'dataset'):
            dataset = dataset.dataset
        assert dataset.num_sat_frames == 1
