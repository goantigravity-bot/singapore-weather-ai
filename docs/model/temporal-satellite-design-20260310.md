# Temporal Satellite Feature — Design Document

**Date**: 2026-03-10
**Status**: Approved for implementation
**Author**: jinhui + Claude Code

## 1. Motivation

The current WeatherFusionNet V3 uses a **single satellite snapshot** per prediction. This tells the model "there's a cloud here now" but cannot capture **cloud movement direction or speed**. A storm approaching from the northwest looks identical to one moving away — the model must guess.

By feeding 6 consecutive satellite frames (60 minutes of history), the model can learn:
- **Cloud movement vector** — direction and speed
- **Cloud development** — growing (convection developing) or dissipating
- **Spatial approach** — whether the cloud mass is heading toward the target location

This is the difference between nowcasting ("what's happening") and forecasting ("what's coming").

## 2. Design Decision: 6 Frames (60 Minutes)

We chose **6 frames at 10-minute intervals** to match the sensor branch's existing time window:

- Sensor branch: 6 timesteps × 10 min = 60 min history
- Satellite branch: 6 frames × 10 min = 60 min history

Both branches see the same temporal horizon. This symmetry allows the cross-attention fusion layer to align temporal patterns across modalities — for example, "humidity rising over 60 min" (sensor) + "cloud mass approaching over 60 min" (satellite) together signal rain more strongly than either alone.

Alternatives considered:
- **3 frames (30 min)** — rejected because it misses slower-moving weather systems and creates asymmetry with the sensor window
- **Configurable** — unnecessary complexity at this stage; we can change the value later if needed

## 3. What the 3 Satellite Channels Capture Over Time

Each frame contains 3 channels. The temporal sequence allows the GRU to track not just cloud movement, but **cloud development and rain potential** across all 3 physical dimensions:

| Channel | Wavelength | Physical Property | What it sees | Temporal signal (across 6 frames) |
|---------|-----------|-------------------|-------------|----------------------------------|
| **B08** | 6.2μm | Water vapor | Upper-level moisture distribution | Tracks moisture flow at high altitude — early signal of approaching weather systems |
| **B11** | 8.6μm | Cloud phase | Ice vs water droplets in clouds | Cloud maturation: water → ice transition means convection intensifying |
| **B13** | 10.4μm | Thermal IR | Cloud top temperature (TBB) | Cloud vertical growth: rapidly cooling tops signal active convection |

### Example: What the GRU learns from 6 frames × 3 channels

```text
Frame 1 → Frame 2 → Frame 3 → Frame 4 → Frame 5 → Frame 6

B08:  moisture here → moving SE → moving SE → closer → closer → overhead
B11:  water cloud   → water     → mixed     → ice    → ice    → ice
B13:  warm (290K)   → cooling   → cooling   → cold   → colder → 240K
                                                                   ↓
                                                       GRU learns: "moisture approaching
                                                       + cloud freezing + top cooling
                                                       = heavy rain imminent"
```

The 3 channels give the GRU a **3D thermodynamic view** of cloud evolution over time:

- **B08 tracks horizontal movement** — where the moisture is going
- **B11 tracks phase change** — whether the cloud is developing (water→ice) or dissipating (ice→water)
- **B13 tracks vertical growth** — taller clouds (colder tops) mean stronger convection and heavier rain

A single frame can show "there's a cold ice-topped cloud here." Six frames can show "this cloud appeared 40 minutes ago as warm water droplets, grew vertically, froze, and is now directly overhead" — a much stronger rain signal.

## 4. Architecture Decision: Shared ResNet + GRU (Approach A)

Three approaches were evaluated:

### Approach A: Shared ResNet + GRU (selected)

```
6 frames → Shared ResNet extracts spatial features per frame → GRU sequences them → 256d
```

- Already implemented as `TemporalSatelliteEncoder` in `weather_fusion_model.py`
- Parameter efficient (~1.5M params, same as current model)
- GRU is purpose-built for short ordered sequences
- Training: ~45-60 min on T4

### Approach B: 3D Convolution (Conv3D) — rejected

```
6 frames stacked as (B, C, T, H, W) → 3D CNN extracts spatiotemporal features
```

- Learns motion patterns directly from pixels
- **Rejected because**: at 41×37 resolution, the 2D ResNet's receptive field already covers the entire image — no spatial information is lost when summarizing each frame to a 256d vector. Conv3D would add ~3× parameters (overfitting risk with only ~2% rain samples) and ~2× memory, likely requiring batch size reduction below practical levels on T4 (15GB VRAM). Conv3D shines at higher resolutions (256×256+) where fine-grained spatiotemporal patterns exist in the pixels.

### Approach C: Shared ResNet + Temporal Attention — rejected

```
6 frames → Shared ResNet per frame → Self-Attention across frames → 256d
```

- Attention can learn which frames matter most
- **Rejected because**: self-attention on 6 tokens is overkill. The computational overhead of query/key/value projections adds no benefit over GRU for such short sequences. Attention excels when the sequence is long and the model needs to selectively focus on distant positions.

### Why Approach A is the right fit

The two-stage design (ResNet per frame → GRU across frames) works well because:

1. **ResNet extracts "what's in each frame"** — cloud positions, intensity, coverage
2. **GRU learns "how it changed across frames"** — movement, development, approach

At 41×37 resolution, each frame can be fully summarized into a compact 256d vector without losing information. The temporal relationship is then a clean sequential pattern that GRU handles naturally.

## 5. Data Pipeline: Sliding Window

Training samples use a **sliding window with 10-minute stride**:

```
Sample 1:
  Sensor:    [00:00, 00:10, 00:20, 00:30, 00:40, 00:50]
  Satellite: [00:00, 00:10, 00:20, 00:30, 00:40, 00:50]
  Target:    01:00 rainfall (binary: rain > 0.1mm)

Sample 2:
  Sensor:    [00:10, 00:20, 00:30, 00:40, 00:50, 01:00]
  Satellite: [00:10, 00:20, 00:30, 00:40, 00:50, 01:00]
  Target:    01:10 rainfall

Sample 3:
  Sensor:    [00:20, 00:30, 00:40, 00:50, 01:00, 01:10]
  Satellite: [00:20, 00:30, 00:40, 00:50, 01:00, 01:10]
  Target:    01:20 rainfall
```

Windows overlap by 5 frames (50 min). This is standard in time-series ML — the model learns generalizable patterns ("humidity rising + clouds approaching → rain"), not specific timestamps. With 6 years of data, this yields millions of training samples.

## 6. Training Plan

| Parameter | Value |
|-----------|-------|
| Server | g4dn.xlarge (T4 15GB VRAM) |
| Satellite frames | 6 (60 min) |
| Batch size | 256-512 (reduced from 1024 due to 6× satellite memory) |
| Epochs | 30 |
| Estimated training time | 45-60 min |
| Loss function | Focal Loss + Physics Constraint (unchanged) |
| Optimizer | AdamW + Cosine Annealing (unchanged) |

## 7. Deployment Strategy

**Evaluate before deploying** — no risk to production:

1. Train new temporal model on Training Server → saves new `.pth` checkpoint
2. Evaluate using `diagnose_model.py` — compare F1, precision, recall against current V3 baseline
3. **Only if metrics improve** → deploy new model + updated `predict.py` to API Server
4. If metrics do not improve → current V3 remains in production, investigate and iterate

## 8. Files to Change

| File | Change |
|------|--------|
| `services/training/weather_dataset.py` | `__getitem__()`: load 6 satellite frames instead of 1 |
| `services/training/train_direct.py` | Set `num_sat_frames=6` when creating model |
| `services/training/diagnose_model.py` | Load model with `num_sat_frames=6` for evaluation |
| `services/api/backend/predict.py` | Fetch 6 consecutive satellite images at inference time |

The model architecture code (`weather_fusion_model.py`) requires **no changes** — `TemporalSatelliteEncoder` and the `num_sat_frames` parameter already exist.

## 9. Expected Impact

| Metric | Current (single frame) | Expected (6 frames) |
|--------|----------------------|---------------------|
| Rain detection F1 | ~52.9% | ~60-65% (estimated) |
| False positives | High | Lower (model knows cloud direction) |
| Prediction lead time | ~10 min | ~10-20 min (detects approaching rain earlier) |
| Training time | ~20 min | ~45-60 min |
| Inference latency | ~200ms | ~300-400ms (6× satellite fetch + CNN forward) |

## 10. Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Missing satellite frames (gaps in 10-min data) | Zero-fill missing frames — model already handles zero satellite input gracefully |
| 6× memory per sample exceeds T4 VRAM | Reduce batch size from 1024 → 256-512 |
| No improvement over single frame | Keep current V3 in production; investigate whether GRU is learning temporal patterns via gradient analysis |
| Increased inference latency | 6 NPY files are ~6KB each (37KB total) — S3 fetch is parallelizable |

## 11. Future Iteration: Increasing Frame Count (12 or 18)

The `num_sat_frames` parameter is configurable — changing from 6 to 12 is a one-line change. However, more frames involve real trade-offs that should be considered after evaluating the 6-frame baseline.

### What more frames capture

| Frames | Time Window | Weather Pattern |
|--------|------------|-----------------|
| 6 | 60 min | Fast-moving storms, local convection (typical Singapore afternoon thunderstorm) |
| 12 | 120 min | Slower monsoon fronts, squall lines approaching from distance |
| 18 | 180 min | Large-scale weather system movement (inter-monsoon transitions) |

### Trade-off analysis

| Factor | 6 frames | 12 frames | 18 frames |
|--------|----------|-----------|-----------|
| Memory per sample | ~37KB | ~74KB | ~111KB |
| Batch size (T4 15GB) | 256-512 | 128-256 | 64-128 |
| Training time | ~45-60 min | ~90-120 min | ~150-180 min |
| Missing frame probability | Low | Medium | High |
| GRU sequence learning | Easy (short) | Moderate | Hard (long-range dependency) |

### Why 6 frames is the right starting point

Singapore's dominant rain pattern — afternoon convective storms — forms in 30-60 min and moves across the island in 20-40 min. Six frames (60 min) captures this lifecycle fully.

### When to try 12 frames

If the 6-frame model shows clear improvement and we want to also capture **monsoon rain bands** (which approach over 2-4 hours), try 12 frames as a second experiment. This is a one-line config change with no architecture modifications.

### When to consider architecture changes

At 18 frames, GRU struggles with long-range dependencies — the earliest frames contribute diminishing signal to the final hidden state. Additionally, the probability of hitting a satellite data gap (missing frame) increases significantly, injecting noise via zero-fill.

If 12 frames shows benefit and longer windows are desired, the next step would be replacing GRU with a **small Transformer** (4-head self-attention over frame embeddings). Attention handles long sequences better than GRU because it can directly relate any frame to any other frame, regardless of distance in the sequence.

### Recommended experiment sequence

1. **6 frames + GRU** (this implementation) → evaluate
2. If improved: **12 frames + GRU** (config change only) → evaluate
3. If 12 helps and longer is desired: **12+ frames + Transformer** (architecture change) → new design doc
