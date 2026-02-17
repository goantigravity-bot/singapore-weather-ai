"""
hsd_parser.py — 轻量 Himawari HSD 二进制解析器

替代 satpy 的完整 Scene/reader/dask/xarray 链，仅提取亮温数据。
HSD 文件由 11 个 header blocks + data 区组成，全部 little-endian。

标定流程: 16-bit count → radiance (gain/offset) → brightness temperature (Planck 修正)

参考:
  - Himawari Standard Data User's Guide v1.3
  - satpy.readers.ahi_hsd (验证基准, max diff < 0.0001K)
"""

import bz2
import struct
from pathlib import Path

import numpy as np

# 新加坡+柔佛 crop bounds (segment-local 索引, 含 5 像素 padding)
# 已用 satpy 验证: global rows[2655:2696] cols[891:928] → segment-local rows[455:496]
# 对所有 R20 S0510 segment 文件固定不变 (投影和分辨率恒定)
SG_CROP_BOUNDS = (455, 496, 891, 928)  # (row_min, row_max, col_min, col_max) → shape (41, 37)


def _walk_blocks(raw: bytes) -> dict[int, tuple[int, int]]:
    """遍历 HSD 的 11 个 header blocks，返回 {block_no: (offset, length)}"""
    blocks = {}
    offset = 0
    for _ in range(11):
        bn = raw[offset]
        bl = struct.unpack_from("<H", raw, offset + 1)[0]
        blocks[bn] = (offset, bl)
        offset += bl
    return blocks


def _parse_block5(raw: bytes, blocks: dict) -> dict:
    """Block 5: Calibration Information — count→radiance 线性转换参数"""
    off = blocks[5][0] + 3  # skip block_no(1) + length(2)
    band_no = struct.unpack_from("<H", raw, off)[0]; off += 2
    central_wave = struct.unpack_from("<d", raw, off)[0]; off += 8
    off += 2  # skip valid_bits
    error_count = struct.unpack_from("<H", raw, off)[0]; off += 2
    outside_count = struct.unpack_from("<H", raw, off)[0]; off += 2
    gain = struct.unpack_from("<d", raw, off)[0]; off += 8
    constant = struct.unpack_from("<d", raw, off)[0]; off += 8

    # Planck 修正系数 (紧跟 gain/constant)
    c0 = struct.unpack_from("<d", raw, off)[0]; off += 8
    c1 = struct.unpack_from("<d", raw, off)[0]; off += 8
    c2 = struct.unpack_from("<d", raw, off)[0]; off += 8

    # skip c0/c1/c2_tb2rad (反向转换, 不需要)
    off += 24
    speed_of_light = struct.unpack_from("<d", raw, off)[0]; off += 8
    planck_h = struct.unpack_from("<d", raw, off)[0]; off += 8
    boltzmann_k = struct.unpack_from("<d", raw, off)[0]

    return {
        "band_no": band_no,
        "central_wave_um": central_wave,
        "gain": gain, "constant": constant,
        "error_count": error_count,
        "outside_count": outside_count,
        "c0": c0, "c1": c1, "c2": c2,
        "planck_h": planck_h,
        "speed_of_light": speed_of_light,
        "boltzmann_k": boltzmann_k,
    }


def _read_counts(raw: bytes, blocks: dict) -> np.ndarray:
    """从 data 区提取 16-bit count 数组 (550 × 5500 for R20 segments)"""
    # data 紧跟 11 个 header blocks，无额外 header
    data_offset = sum(blocks[bn][1] for bn in range(1, 12))
    ncols = 5500
    nlines = (len(raw) - data_offset) // (ncols * 2)
    counts = np.frombuffer(raw, dtype="<u2", offset=data_offset, count=nlines * ncols)
    return counts.reshape(nlines, ncols)


def _count_to_bt(counts: np.ndarray, cal: dict) -> np.ndarray:
    """count → radiance → brightness temperature (Kelvin)

    使用 HSD 内置 Planck 常量和修正系数，精度与 satpy 一致 (< 0.0001K)。
    """
    arr = counts.astype(np.float64)
    invalid = (counts == cal["error_count"]) | (counts == cal["outside_count"]) | (counts == 0)

    # count → radiance (线性)
    radiance = cal["gain"] * arr + cal["constant"]
    radiance[invalid] = np.nan

    # radiance → effective temperature (逆 Planck)
    h, c, k = cal["planck_h"], cal["speed_of_light"], cal["boltzmann_k"]
    wl = cal["central_wave_um"] * 1e-6  # μm → m
    C1 = 2 * h * c ** 2
    C2 = h * c / k

    # HSD radiance 单位是 W/(m²·sr·μm)，Planck 公式需要 W/(m²·sr·m)
    rad_si = radiance * 1e6

    with np.errstate(invalid="ignore", divide="ignore"):
        teff = C2 / (wl * np.log(1.0 + C1 / (wl ** 5 * rad_si)))

    # Planck 修正: BT = c0 + c1*Teff + c2*Teff²
    bt = cal["c0"] + cal["c1"] * teff + cal["c2"] * teff ** 2
    return bt.astype(np.float32)


def parse_hsd(filepath: str | Path,
              crop_bounds: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """解析单个 HSD .bz2 文件，返回亮温数组 (float32, Kelvin)

    Args:
        filepath: HSD .bz2 文件路径
        crop_bounds: (row_min, row_max, col_min, col_max) segment-local 裁剪范围
    """
    with open(filepath, "rb") as f:
        raw = bz2.decompress(f.read())

    blocks = _walk_blocks(raw)
    cal = _parse_block5(raw, blocks)
    counts = _read_counts(raw, blocks)
    bt = _count_to_bt(counts, cal)

    if crop_bounds is not None:
        r_min, r_max, c_min, c_max = crop_bounds
        bt = bt[r_min:r_max, c_min:c_max]

    return bt
