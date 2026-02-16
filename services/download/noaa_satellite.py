"""
NOAA Himawari-9 卫星数据下载模块

从 AWS Open Data (noaa-himawari9) 下载 ISatSS C13 红外亮温 tile，
裁剪新加坡+周边区域 128×128，保存为 .npy。

数据源: s3://noaa-himawari9/AHI-L2-FLDK-ISatSS/YYYY/MM/DD/HHMM/
Tile: T036 (覆盖 ~0.05°N~2.65°N, 102.5°E~105.1°E)
波段: C13 (Band 13, 10.41μm) → Sectorized_CMI (brightness temperature, Kelvin)
"""
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta

import numpy as np

logger = logging.getLogger(__name__)

# ─── NOAA S3 配置 ───
NOAA_BUCKET = "noaa-himawari9"
NOAA_PRODUCT = "AHI-L2-FLDK-ISatSS"
TILE_ID = "T036"        # 覆盖新加坡区域的 tile
BAND = "M1C13"          # Band 13 红外
TILE_PATTERN = f"{BAND}-{TILE_ID}"

# ─── 裁剪参数 ───
# SG center 在 tile T036 中的行列位置 (全盘 5500×5500, tile 550×550)
# 全盘 SG center: row=479, col=360 (tile 内坐标)
# 裁剪 ±64 像素 → 128×128 原始分辨率
_SG_ROW_CENTER = 479
_SG_COL_CENTER = 360
_HALF_SIZE = 64
CROP_ROW_MIN = _SG_ROW_CENTER - _HALF_SIZE   # 415
CROP_ROW_MAX = _SG_ROW_CENTER + _HALF_SIZE   # 543
CROP_COL_MIN = _SG_COL_CENTER - _HALF_SIZE   # 296
CROP_COL_MAX = _SG_COL_CENTER + _HALF_SIZE   # 424
TARGET_SIZE = (128, 128)

# 输出 bounds (用于前端 Leaflet 叠加)
# 约覆盖: 0.05°N~2.65°N, 102.5°E~105.1°E
SG_BOUNDS = [[0.05, 102.5], [2.65, 105.1]]

# .npy 文件名格式
NPY_TEMPLATE = "SAT_128_{date}_{slot}.npy"


def build_s3_prefix(dt_utc: datetime) -> str:
    """
    构建 NOAA S3 路径前缀。
    ISatSS 按 10 分钟 UTC 时间戳组织: YYYY/MM/DD/HHMM/
    注意: 输入必须是 UTC 时间。
    """
    return (
        f"{NOAA_PRODUCT}/"
        f"{dt_utc.strftime('%Y')}/"
        f"{dt_utc.strftime('%m')}/"
        f"{dt_utc.strftime('%d')}/"
        f"{dt_utc.strftime('%H%M')}/"
    )


def find_tile_filename(dt_utc: datetime) -> str | None:
    """
    在 NOAA S3 中查找指定时间戳的 C13-T036 tile 文件名。
    返回完整文件名 (不含路径)，找不到返回 None。
    """
    prefix = build_s3_prefix(dt_utc)
    s3_path = f"s3://{NOAA_BUCKET}/{prefix}"

    result = subprocess.run(
        ["aws", "s3", "ls", "--no-sign-request", s3_path],
        capture_output=True, text=True, timeout=30
    )

    if result.returncode != 0:
        logger.warning(f"S3 list failed for {s3_path}: {result.stderr.strip()}")
        return None

    for line in result.stdout.strip().split("\n"):
        if TILE_PATTERN in line:
            parts = line.strip().split()
            if len(parts) >= 4:
                return parts[-1]

    logger.warning(f"Tile {TILE_PATTERN} not found at {s3_path}")
    return None


def download_tile(dt_utc: datetime, output_dir: str) -> str | None:
    """
    从 NOAA S3 下载 C13-T036 tile 到本地。
    返回本地文件路径，失败返回 None。
    """
    filename = find_tile_filename(dt_utc)
    if not filename:
        return None

    prefix = build_s3_prefix(dt_utc)
    s3_url = f"s3://{NOAA_BUCKET}/{prefix}{filename}"
    local_path = os.path.join(output_dir, filename)

    result = subprocess.run(
        ["aws", "s3", "cp", "--no-sign-request", s3_url, local_path],
        capture_output=True, text=True, timeout=60
    )

    if result.returncode != 0 or not os.path.exists(local_path):
        logger.error(f"Download failed: {s3_url}")
        return None

    size_kb = os.path.getsize(local_path) // 1024
    logger.debug(f"Downloaded {filename} ({size_kb}KB)")
    return local_path


def crop_tile_to_npy(nc_path: str) -> np.ndarray | None:
    """
    将 ISatSS tile .nc 裁剪为新加坡区域 128×128 numpy 数组。

    读取 Sectorized_CMI 变量（netCDF4 自动 scale/offset → Kelvin），
    裁剪中心 128×128 像素区域。
    """
    try:
        import netCDF4 as nc

        ds = nc.Dataset(nc_path, "r")
        # netCDF4 自动应用 scale_factor 和 add_offset → 直接得到 Kelvin
        # 返回 MaskedArray，需要 filled() 转为普通 ndArray
        tbb_raw = ds.variables["Sectorized_CMI"][:]
        tbb = np.ma.filled(tbb_raw, fill_value=np.nan)
        ds.close()

        # 裁剪 SG 区域
        crop = tbb[CROP_ROW_MIN:CROP_ROW_MAX, CROP_COL_MIN:CROP_COL_MAX]
        final = crop.astype(np.float32)

        if final.shape != TARGET_SIZE:
            # 万一 tile 边界不够，用 interpolate 补齐
            import torch
            import torch.nn.functional as F
            tensor = torch.tensor(final).unsqueeze(0).unsqueeze(0)
            resized = F.interpolate(tensor, size=TARGET_SIZE, mode="bilinear", align_corners=False)
            final = resized.squeeze().numpy()

        return final

    except Exception as e:
        logger.error(f"Error cropping {nc_path}: {e}")
        return None


def make_npy_filename(dt_sgt: datetime) -> str:
    """生成标准 .npy 文件名: SAT_YYYYMMDD_HHMM.npy (使用 SGT 时间)"""
    return NPY_TEMPLATE.format(
        date=dt_sgt.strftime("%Y%m%d"),
        slot=dt_sgt.strftime("%H%M"),
    )


def download_and_crop(dt_sgt: datetime, output_dir: str | None = None) -> tuple[np.ndarray | None, str]:
    """
    完整流程: 下载 tile → 裁剪 128×128 → 返回 (numpy_array, npy_filename)。

    Args:
        dt_sgt: SGT 时间戳（文件名用 SGT，S3 查找内部转 UTC）
        output_dir: 临时文件目录（不传则自动创建）

    Returns:
        (128×128 float32 array, "SAT_YYYYMMDD_HHMM.npy") 或 (None, "")
    """
    npy_name = make_npy_filename(dt_sgt)
    # SGT → UTC 仅用于构建 S3 路径
    dt_utc = dt_sgt - timedelta(hours=8)
    cleanup = False

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="noaa_")
        cleanup = True

    try:
        nc_path = download_tile(dt_utc, output_dir)
        if nc_path is None:
            return None, ""

        arr = crop_tile_to_npy(nc_path)

        # 清理下载的 .nc
        if os.path.exists(nc_path):
            os.remove(nc_path)

        return arr, npy_name

    finally:
        if cleanup and os.path.isdir(output_dir):
            import shutil
            shutil.rmtree(output_dir, ignore_errors=True)


def sgt_to_utc(sgt_str: str) -> datetime:
    """SGT 时间字符串 → UTC datetime。格式: 'YYYY-MM-DD HH:MM' 或 'YYYYMMDD_HHMM'。"""
    for fmt in ["%Y-%m-%d %H:%M", "%Y%m%d_%H%M"]:
        try:
            sgt = datetime.strptime(sgt_str, fmt)
            return sgt - timedelta(hours=8)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse SGT time: {sgt_str}")


def npy_to_cloud_png(arr: np.ndarray, out_path: str) -> bool:
    """将 128×128 TBB numpy 数组渲染为 512×512 RGBA 云图 PNG。

    颜色映射：TBB 越低 → 云越厚（白色、高 alpha）；TBB ≥ 290K → 晴空（透明）。
    与 api.py 中 _npy_to_base64_png 逻辑保持一致。
    """
    try:
        from PIL import Image

        tbb_min, tbb_max = 200.0, 290.0
        alpha = np.clip((tbb_max - arr) / (tbb_max - tbb_min), 0.0, 1.0)

        rgba = np.zeros((*arr.shape, 4), dtype=np.uint8)
        rgba[:, :, 0] = 255  # R
        rgba[:, :, 1] = 255  # G
        rgba[:, :, 2] = 255  # B
        rgba[:, :, 3] = (alpha * 220).astype(np.uint8)

        img = Image.fromarray(rgba, 'RGBA')
        img = img.resize((512, 512), Image.BILINEAR)
        img.save(out_path, format='PNG', optimize=True)
        return True
    except Exception as e:
        logger.error(f"PNG render failed: {e}")
        return False


# ─── CLI 入口：测试单帧下载 ───
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    if len(sys.argv) > 1:
        ts = sgt_to_utc(sys.argv[1])
    else:
        # 默认: 当前时间往回找最近 10 分钟整
        now_utc = datetime.utcnow()
        ts = now_utc.replace(minute=(now_utc.minute // 10) * 10, second=0, microsecond=0)
        ts -= timedelta(minutes=20)  # 延迟 ~20 分钟

    logger.info(f"Target: {ts.strftime('%Y-%m-%d %H:%M')} UTC")

    arr, name = download_and_crop(ts)
    if arr is not None:
        np.save(name, arr)
        logger.info(f"✅ Saved {name}: shape={arr.shape}, TBB={arr.min():.0f}~{arr.max():.0f}K")
    else:
        logger.error("❌ Failed")
