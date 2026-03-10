# Temporal Satellite Feature — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable the WeatherFusionNet model to use 6 consecutive satellite frames (60 min) instead of 1, so it can learn cloud movement and development patterns for better rain prediction.

**Architecture:** The existing `TemporalSatelliteEncoder` (shared ResNet + GRU) is already implemented in `weather_fusion_model.py`. The work is in the data pipeline: loading 6 frames in the dataset, passing `num_sat_frames=6` during training, and fetching 6 frames at inference time.

**Tech Stack:** PyTorch, NumPy, existing WeatherFusionNet V3 model code

**Spec:** `docs/model/temporal-satellite-design-20260310.md`

---

## File Map

| File | Action | Responsibility |
| ---- | ------ | -------------- |
| `services/training/weather_dataset.py` | Modify | Load 6 satellite frames per sample instead of 1 |
| `services/training/train_direct.py` | Modify | Pass `num_sat_frames=6` when creating model |
| `services/training/diagnose_model.py` | Modify | Load model with `num_sat_frames=6` for evaluation |
| `services/api/backend/predict.py` | Modify | Fetch 6 consecutive satellite images at inference |
| `services/training/weather_fusion_model.py` | No change | `TemporalSatelliteEncoder` already exists |

---

## Task 1: Update WeatherDataset to load 6 satellite frames

**Files:**

- Modify: `services/training/weather_dataset.py:76-87` (constructor — add `num_sat_frames` param)
- Modify: `services/training/weather_dataset.py:265-330` (`__getitem__` — load 6 frames)

- [ ] **Step 1: Add `num_sat_frames` parameter to `WeatherDataset.__init__`**

In the constructor (line 83), add the parameter and store it:

```python
def __init__(self, csv_file, sat_dir, sequence_length=6, prediction_horizon=1, num_sat_frames=1):
    # ... existing code ...
    self.num_sat_frames = num_sat_frames
```

- [ ] **Step 2: Update `__getitem__` to load multiple satellite frames**

Replace the single-frame satellite loading block (lines 316-324) with multi-frame loading.

Current code (single frame):

```python
# 3. 卫星图
utc_str = self._sat_utc_cache[sensor_id][input_end - 1]
data = self._sat_cache.get(utc_str)
if data is not None:
    sat_img = torch.tensor(data, dtype=torch.float32)
    sat_img = (sat_img - 200) / 100.0
    sat_img = torch.nan_to_num(sat_img, nan=0.0)
else:
    sat_img = torch.zeros(len(SAT_BANDS), SAT_HEIGHT, SAT_WIDTH)
```

New code (multi-frame):

```python
# 3. 卫星图（单帧或多帧）
if self.num_sat_frames > 1:
    frames = []
    for offset in range(self.num_sat_frames):
        idx = input_end - self.num_sat_frames + offset
        if idx >= 0 and idx < len(self._sat_utc_cache[sensor_id]):
            utc_str = self._sat_utc_cache[sensor_id][idx]
            data = self._sat_cache.get(utc_str)
        else:
            data = None
        if data is not None:
            frame = torch.tensor(data, dtype=torch.float32)
            frame = (frame - 200) / 100.0
            frame = torch.nan_to_num(frame, nan=0.0)
        else:
            frame = torch.zeros(len(SAT_BANDS), SAT_HEIGHT, SAT_WIDTH)
        frames.append(frame)
    sat_img = torch.stack(frames)  # (T, C, H, W)
else:
    utc_str = self._sat_utc_cache[sensor_id][input_end - 1]
    data = self._sat_cache.get(utc_str)
    if data is not None:
        sat_img = torch.tensor(data, dtype=torch.float32)
        sat_img = (sat_img - 200) / 100.0
        sat_img = torch.nan_to_num(sat_img, nan=0.0)
    else:
        sat_img = torch.zeros(len(SAT_BANDS), SAT_HEIGHT, SAT_WIDTH)
```

- [ ] **Step 3: Update `get_dataloaders` to pass `num_sat_frames` through**

In `get_dataloaders()` function (line 367), add the parameter:

```python
def get_dataloaders(csv_path, sat_dir, batch_size=4, split=0.8, temporal_split=True, num_sat_frames=1):
    dataset = WeatherDataset(csv_path, sat_dir, num_sat_frames=num_sat_frames)
    # ... rest unchanged ...
```

- [ ] **Step 4: Verify locally with a quick smoke test**

Run on Training Server:

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> "
cd ~/weather-ai/services/training && source ~/weather-ai/venv/bin/activate &&
python3 -c \"
from weather_dataset import WeatherDataset
ds = WeatherDataset('data/sensor_data.csv', 'data/satellite-3ch', num_sat_frames=6)
sat, sensor, coord, target = ds[0]
print(f'sat shape: {sat.shape}')    # expect (6, 3, 41, 37)
print(f'sensor shape: {sensor.shape}')  # expect (6, 13)
print(f'coord shape: {coord.shape}')    # expect (2,)
print(f'target shape: {target.shape}')  # expect (1,)
\"
"
```

Expected output: `sat shape: torch.Size([6, 3, 41, 37])`

- [ ] **Step 5: Commit**

```bash
git add services/training/weather_dataset.py
git commit -m "feat: WeatherDataset supports multi-frame satellite loading (num_sat_frames)"
```

---

## Task 2: Update train_direct.py to train with 6 frames

**Files:**

- Modify: `services/training/train_direct.py:76-78` (model creation)
- Modify: `services/training/train_direct.py:221-225` (argparse)

- [ ] **Step 1: Add `--sat-frames` CLI argument**

In the argparse section (around line 221):

```python
parser.add_argument("--sat-frames", type=int, default=1,
                    help="Number of satellite frames (1=single, 6=temporal)")
```

- [ ] **Step 2: Pass `num_sat_frames` to model and dataloader**

Update model creation (line 76-78):

```python
model = WeatherFusionNet(
    sat_channels=3, sensor_features=13, coord_dim=2,
    num_sat_frames=args.sat_frames, use_cross_attention=True
)
```

Update dataloader creation to pass `num_sat_frames=args.sat_frames` to `get_dataloaders()`.

- [ ] **Step 3: Save `num_sat_frames` in checkpoint metadata**

After training completes, when saving the model, also save the config so `predict.py` and `diagnose_model.py` know what to expect:

```python
torch.save({
    'model_state_dict': model.state_dict(),
    'num_sat_frames': args.sat_frames,
}, model_path)
```

Note: This changes the checkpoint format from a plain `state_dict` to a dict. Update the loading code in the same file (incremental training section, around line 85-90) to handle both formats:

```python
checkpoint = torch.load(MODEL_PATH, map_location=device, weights_only=False)
if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
    model.load_state_dict(checkpoint['model_state_dict'])
else:
    model.load_state_dict(checkpoint)
```

- [ ] **Step 4: Reduce default batch size for GPU**

The current default batch size detection (around line 70) needs adjustment for 6-frame satellite data. With 6× satellite memory, reduce CUDA batch size:

```python
if device.type == "cuda":
    batch_size = args.batch_size or 384   # was 1024; 6× satellite memory
```

- [ ] **Step 5: Commit**

```bash
git add services/training/train_direct.py
git commit -m "feat: train_direct.py supports temporal satellite via --sat-frames flag"
```

---

## Task 3: Update diagnose_model.py for evaluation

**Files:**

- Modify: `services/training/diagnose_model.py:37-38` (model loading)

- [ ] **Step 1: Update model loading to read `num_sat_frames` from checkpoint**

Replace lines 37-38:

```python
# Load checkpoint (supports both old state_dict and new dict format)
checkpoint = torch.load(MODEL_PATH, map_location=device, weights_only=False)
if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
    num_sat_frames = checkpoint.get('num_sat_frames', 1)
    state_dict = checkpoint['model_state_dict']
else:
    num_sat_frames = 1
    state_dict = checkpoint

model = WeatherFusionNet(
    sat_channels=3, sensor_features=13, coord_dim=2,
    num_sat_frames=num_sat_frames, use_cross_attention=True
)
model.load_state_dict(state_dict)
```

- [ ] **Step 2: Pass `num_sat_frames` to dataloader**

Update the `get_dataloaders()` call in `diagnose()` to pass `num_sat_frames=num_sat_frames`.

- [ ] **Step 3: Commit**

```bash
git add services/training/diagnose_model.py
git commit -m "feat: diagnose_model.py auto-detects num_sat_frames from checkpoint"
```

---

## Task 4: Update predict.py for inference with 6 frames

**Files:**

- Modify: `services/api/backend/predict.py:64-73` (`load_system` — read checkpoint metadata)
- Modify: `services/api/backend/predict.py:205-272` (`get_input_data` — fetch 6 satellite images)

- [ ] **Step 1: Update `load_system()` to read `num_sat_frames` from checkpoint**

Replace model loading in `load_system()` (lines 64-74):

```python
def load_system():
    print("Loading Model...")
    # Load checkpoint and detect num_sat_frames
    num_sat_frames = 1
    if os.path.exists(MODEL_PATH):
        try:
            checkpoint = torch.load(MODEL_PATH, map_location=DEVICE, weights_only=False)
            if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                num_sat_frames = checkpoint.get('num_sat_frames', 1)
                state_dict = checkpoint['model_state_dict']
            else:
                state_dict = checkpoint

            model = WeatherFusionNet(
                sat_channels=SAT_CHANNELS, sensor_features=13, coord_dim=2,
                num_sat_frames=num_sat_frames
            )
            model.load_state_dict(state_dict)
            model.num_sat_frames = num_sat_frames  # store for get_input_data
            print(f"Model loaded (num_sat_frames={num_sat_frames}).")
        except Exception as e:
            print(f"⚠️ Error loading model: {e}")
            model = WeatherFusionNet(sat_channels=SAT_CHANNELS, sensor_features=13, coord_dim=2)
            model.num_sat_frames = 1
    else:
        print(f"Warning: {MODEL_PATH} not found. Using random weights.")
        model = WeatherFusionNet(sat_channels=SAT_CHANNELS, sensor_features=13, coord_dim=2)
        model.num_sat_frames = 1

    # ... rest of load_system (CSV loading) unchanged ...
```

- [ ] **Step 2: Add helper function to load a single satellite frame**

Extract the existing satellite loading logic into a reusable function:

```python
def _load_single_satellite_frame(utc_str):
    """Load one 3-channel satellite frame by UTC timestamp string.
    Returns (3, H, W) tensor or None if unavailable."""
    processed_dir = "processed_data"
    band_data = {}
    for band in SAT_BANDS:
        pattern = f"SAT_{band}_{utc_str}*.npy"
        matches = glob.glob(os.path.join(processed_dir, pattern))
        if matches:
            try:
                band_data[band] = np.load(matches[0])
            except Exception:
                pass

    if len(band_data) == SAT_CHANNELS:
        layers = [band_data[b] for b in SAT_BANDS]
        stacked = np.stack(layers, axis=0)
        tensor = torch.tensor(stacked, dtype=torch.float32)
        tensor = torch.nan_to_num(tensor, nan=0.0)
        tensor = (tensor - 200) / 100.0
        return tensor
    return None
```

- [ ] **Step 3: Update `get_input_data()` to load 6 frames when model requires it**

Replace the satellite loading section (lines 205-272) in `get_input_data()`. Add `num_sat_frames` parameter:

```python
def get_input_data(sensor_id, target_time, df, station_lat=None, station_lon=None, num_sat_frames=1):
    # ... sensor feature construction unchanged (lines 140-203) ...

    # 2. Fetch Satellite Image(s)
    minute = (target_time.minute // 10) * 10
    sat_ts = target_time.replace(minute=minute, second=0)

    if num_sat_frames > 1:
        frames = []
        for i in range(num_sat_frames):
            frame_time = sat_ts - timedelta(minutes=10 * (num_sat_frames - 1 - i))
            utc_str = (frame_time - timedelta(hours=8)).strftime('%Y%m%d_%H%M')
            frame = _load_single_satellite_frame(utc_str)
            if frame is None:
                frame = torch.zeros(SAT_CHANNELS, SAT_HEIGHT, SAT_WIDTH)
            frames.append(frame)
        sat_tensor = torch.stack(frames).unsqueeze(0)  # (1, T, C, H, W)
    else:
        utc_str = (sat_ts - timedelta(hours=8)).strftime('%Y%m%d_%H%M')
        frame = _load_single_satellite_frame(utc_str)
        if frame is None:
            frame = torch.zeros(SAT_CHANNELS, SAT_HEIGHT, SAT_WIDTH)
        sat_tensor = frame.unsqueeze(0)  # (1, C, H, W)

    # ... coordinate calculation unchanged (lines 264-272) ...
```

- [ ] **Step 4: Update callers of `get_input_data` to pass `num_sat_frames`**

In `predict_ensemble()` (line 274+), where `get_input_data` is called, pass the model's `num_sat_frames`:

```python
sat, sensor, coord = get_input_data(
    sensor_id, time_obj, df,
    station_lat=slat, station_lon=slon,
    num_sat_frames=getattr(model, 'num_sat_frames', 1)
)
```

- [ ] **Step 5: Commit**

```bash
git add services/api/backend/predict.py
git commit -m "feat: predict.py supports multi-frame satellite inference"
```

---

## Task 5: Deploy to Training Server, train, and evaluate

**Files:**

- No code changes — deployment and execution steps

- [ ] **Step 1: Deploy updated training files to Training Server**

```bash
scp -i ~/.ssh/id_rsa services/training/weather_dataset.py ubuntu@<TRAINING_IP>:~/weather-ai/services/training/
scp -i ~/.ssh/id_rsa services/training/train_direct.py ubuntu@<TRAINING_IP>:~/weather-ai/services/training/
scp -i ~/.ssh/id_rsa services/training/diagnose_model.py ubuntu@<TRAINING_IP>:~/weather-ai/services/training/
```

- [ ] **Step 2: Run training with 6 frames**

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> "
cd ~/weather-ai/services/training && source ~/weather-ai/venv/bin/activate &&
python3 train_direct.py \
  --sat-frames 6 \
  --batch-size 384 \
  --epochs 30 \
  --model-path weather_fusion_model_v3_temporal.pth \
  2>&1 | tee /tmp/train_temporal.log
"
```

Expected: ~45-60 min training, saves `weather_fusion_model_v3_temporal.pth`

- [ ] **Step 3: Evaluate with diagnose_model.py**

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> "
cd ~/weather-ai/services/training && source ~/weather-ai/venv/bin/activate &&
python3 diagnose_model.py \
  --model-path weather_fusion_model_v3_temporal.pth \
  2>&1 | tee /tmp/diagnose_temporal.log
"
```

Compare F1, precision, recall against current V3 baseline.

**Decision gate:** Only proceed to Task 6 if temporal model shows improvement.

- [ ] **Step 4: Commit training logs / results**

```bash
git add docs/model/
git commit -m "docs: temporal satellite training results"
```

---

## Task 6: Deploy to API Server (only after evaluation passes)

**Files:**

- Deploy: updated `predict.py` to API Server
- Deploy: trained model checkpoint to API Server (via S3)

- [ ] **Step 1: Upload trained model to S3**

```bash
ssh -i ~/.ssh/id_rsa ubuntu@<TRAINING_IP> "
cd ~/weather-ai/services/training &&
aws s3 cp weather_fusion_model_v3_temporal.pth s3://weather-ai-models-gcc/models/
"
```

- [ ] **Step 2: Deploy updated predict.py to API Server**

```bash
scp -i ~/.ssh/id_rsa services/api/backend/predict.py ubuntu@13.228.95.52:~/weather-ai/services/api/backend/
```

- [ ] **Step 3: Download model on API Server**

```bash
ssh -i ~/.ssh/id_rsa ubuntu@13.228.95.52 "
cd ~/weather-ai/services/api &&
aws s3 cp s3://weather-ai-models-gcc/models/weather_fusion_model_v3_temporal.pth backend/weather_fusion_model_v3.pth
"
```

Note: Save as the production filename (`weather_fusion_model_v3.pth`) to match `MODEL_PATH` in `predict.py`. Keep the old model as backup first:

```bash
ssh -i ~/.ssh/id_rsa ubuntu@13.228.95.52 "
cp ~/weather-ai/services/api/backend/weather_fusion_model_v3.pth \
   ~/weather-ai/services/api/backend/weather_fusion_model_v3_backup.pth
"
```

- [ ] **Step 4: Restart API Server**

```bash
ssh -i ~/.ssh/id_rsa ubuntu@13.228.95.52 "
PID=\$(ss -tlnp | grep 8000 | grep -oP 'pid=\K\d+' | head -1) &&
sudo kill \$PID && sleep 3 &&
cd ~/weather-ai/services/api &&
source ~/weather-ai/venv/bin/activate &&
nohup python3 start.py --workers 1 > /tmp/api.log 2>&1 &
"
```

- [ ] **Step 5: Verify temporal model is loaded**

```bash
ssh -i ~/.ssh/id_rsa ubuntu@13.228.95.52 "grep 'num_sat_frames' /tmp/api.log"
```

Expected: `Model loaded (num_sat_frames=6).`

- [ ] **Step 6: Smoke test a prediction**

```bash
curl -s 'http://13.228.95.52:8000/api/predict?lat=1.35&lon=103.82&location=Singapore' | python3 -m json.tool | head -10
```

- [ ] **Step 7: Commit and push**

```bash
git add services/api/backend/predict.py services/training/
git commit -m "feat: deploy temporal satellite model (6 frames) to production"
git push origin main
```
