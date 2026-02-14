"""
补处理缺失卫星数据

逐日从 S3 下载原始 .nc → 预处理为 64×64 .npy → 上传回 S3 → 清理本地文件。
每步记录耗时和进度，完成后生成 reprocess_report.json。

用法:
  python3 reprocess-missing-satellite.py                     # 处理全部缺失天数
  python3 reprocess-missing-satellite.py --start 2025-10-11  # 从指定日期开始
  python3 reprocess-missing-satellite.py --end 2025-10-29    # 到指定日期截止
  python3 reprocess-missing-satellite.py --dry-run            # 只检查，不处理
"""
import os
import sys
import json
import time
import logging
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime

# 将 training 目录加入 path 以便 import satellite_preprocessor
PROJECT_ROOT = Path(__file__).parent.parent
TRAINING_DIR = PROJECT_ROOT / "services" / "training"
sys.path.insert(0, str(TRAINING_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from satellite_preprocessor import (
    crop_nc_to_npy,
    upload_npy_to_s3,
    check_s3_processed_exists,
    list_raw_nc_keys,
    get_s3_client,
    S3_BUCKET,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ── 路径配置 ──
DATA_DIR = Path(__file__).parent / "data"
TIMESTAMPS_FILE = DATA_DIR / "rainy_timestamps.json"
STATE_FILE = DATA_DIR / "reprocess_state.json"
REPORT_FILE = DATA_DIR / "reprocess_report.json"
RAW_DIR = Path(__file__).parent / "raw-data"


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_processed_date": None, "days_completed": 0}


def save_state(state: dict):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def process_day(s3, day_info: dict, dry_run: bool = False) -> dict:
    """
    处理单日全部降雨时间片。

    Returns:
        该日统计: slots_total, slots_processed, slots_skipped,
        download_time_s, preprocess_time_s, upload_time_s, cleanup_time_s
    """
    date_compact = day_info['date_compact']
    date_str = day_info['date']
    rainy_slots = day_info['rainy_slots']

    stats = {
        "date": date_str,
        "slots_total": len(rainy_slots),
        "slots_processed": 0,
        "slots_skipped": 0,
        "slots_no_raw": 0,
        "slots_failed": 0,
        "download_time_s": 0.0,
        "preprocess_time_s": 0.0,
        "upload_time_s": 0.0,
        "cleanup_time_s": 0.0,
        "total_download_mb": 0.0,
    }

    for idx, slot in enumerate(rainy_slots):
        slot_prefix = f"{date_compact}_{slot}"
        progress = f"[{idx+1}/{len(rainy_slots)}]"

        # 1. 检查是否已处理
        if check_s3_processed_exists(s3, date_compact, slot_prefix):
            stats["slots_skipped"] += 1
            continue

        if dry_run:
            # dry-run 模式只统计需要处理的数量
            nc_keys = list_raw_nc_keys(s3, date_compact, slot_prefix)
            if nc_keys:
                stats["slots_processed"] += 1
            else:
                stats["slots_no_raw"] += 1
            continue

        # 2. 查找 raw .nc
        nc_keys = list_raw_nc_keys(s3, date_compact, slot_prefix)
        if not nc_keys:
            stats["slots_no_raw"] += 1
            continue

        # 3. 逐文件处理
        for nc_key in nc_keys:
            nc_fname = nc_key.split('/')[-1]
            npy_fname = nc_fname.replace('.nc', '.npy')

            RAW_DIR.mkdir(parents=True, exist_ok=True)
            tmp_nc = str(RAW_DIR / nc_fname)
            tmp_npy = str(RAW_DIR / npy_fname)

            try:
                # Phase 1: Download
                t0 = time.time()
                s3.download_file(S3_BUCKET, nc_key, tmp_nc)
                t_download = time.time() - t0
                file_size_mb = os.path.getsize(tmp_nc) / (1024 * 1024)
                stats["download_time_s"] += t_download
                stats["total_download_mb"] += file_size_mb
                logger.info(
                    f"  {progress} ⬇️  {nc_fname} ({file_size_mb:.0f}MB) "
                    f"in {t_download:.1f}s"
                )

                # Phase 2: Preprocess
                t0 = time.time()
                arr = crop_nc_to_npy(tmp_nc)
                t_preprocess = time.time() - t0
                stats["preprocess_time_s"] += t_preprocess

                if arr is None:
                    logger.warning(f"  {progress} ⚠️  Crop failed for {nc_fname}")
                    stats["slots_failed"] += 1
                    continue

                np.save(tmp_npy, arr)
                logger.info(
                    f"  {progress} ✂️  Cropped {arr.shape} "
                    f"in {t_preprocess:.1f}s → {npy_fname}"
                )

                # Phase 3: Upload
                t0 = time.time()
                upload_npy_to_s3(tmp_npy, date_compact, s3=s3, skip_if_exists=False)
                t_upload = time.time() - t0
                stats["upload_time_s"] += t_upload
                logger.info(f"  {progress} ⬆️  Uploaded in {t_upload:.1f}s")

                stats["slots_processed"] += 1

            except Exception as e:
                logger.error(f"  {progress} ❌ Error: {e}")
                stats["slots_failed"] += 1
            finally:
                # Phase 4: Cleanup
                t0 = time.time()
                for tmp in [tmp_nc, tmp_npy]:
                    if os.path.exists(tmp):
                        os.unlink(tmp)
                t_cleanup = time.time() - t0
                stats["cleanup_time_s"] += t_cleanup

    return stats


def generate_report(all_stats: list[dict], total_elapsed: float,
                    dry_run: bool) -> dict:
    """汇总所有日期的统计数据生成最终报告。"""
    total_processed = sum(s["slots_processed"] for s in all_stats)
    total_skipped = sum(s["slots_skipped"] for s in all_stats)
    total_no_raw = sum(s["slots_no_raw"] for s in all_stats)
    total_failed = sum(s["slots_failed"] for s in all_stats)
    total_download_mb = sum(s["total_download_mb"] for s in all_stats)

    report = {
        "generated_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "summary": {
            "total_days": len(all_stats),
            "total_slots_processed": total_processed,
            "total_slots_skipped": total_skipped,
            "total_slots_no_raw": total_no_raw,
            "total_slots_failed": total_failed,
            "total_download_gb": round(total_download_mb / 1024, 2),
            "total_time_seconds": round(total_elapsed, 1),
            "total_time_minutes": round(total_elapsed / 60, 1),
            "avg_time_per_day_seconds": round(
                total_elapsed / len(all_stats), 1
            ) if all_stats else 0,
        },
        "time_breakdown": {
            "download_s": round(
                sum(s["download_time_s"] for s in all_stats), 1
            ),
            "preprocess_s": round(
                sum(s["preprocess_time_s"] for s in all_stats), 1
            ),
            "upload_s": round(
                sum(s["upload_time_s"] for s in all_stats), 1
            ),
            "cleanup_s": round(
                sum(s["cleanup_time_s"] for s in all_stats), 1
            ),
        },
        "per_day": all_stats,
    }
    return report


def main():
    parser = argparse.ArgumentParser(
        description="补处理缺失卫星数据：S3 下载 → 预处理 → 上传 → 清理"
    )
    parser.add_argument("--start", type=str,
                        help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str,
                        help="截止日期 (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true",
                        help="只检查缺失数据，不实际处理")
    parser.add_argument("--resume", action="store_true",
                        help="从上次中断位置继续")
    args = parser.parse_args()

    # 加载缺失日期列表
    if not TIMESTAMPS_FILE.exists():
        logger.error(f"Missing {TIMESTAMPS_FILE}. Run scan_rainy_timestamps.py first.")
        return

    with open(TIMESTAMPS_FILE) as f:
        data = json.load(f)

    days = data['days']
    logger.info(f"Loaded {len(days)} rainy days ({data['total_rainy_slots']} slots)")

    # 日期范围过滤
    if args.start:
        days = [d for d in days if d['date'] >= args.start]
    if args.end:
        days = [d for d in days if d['date'] <= args.end]

    # 断点续传
    if args.resume:
        state = load_state()
        if state['last_processed_date']:
            days = [d for d in days if d['date'] > state['last_processed_date']]
            logger.info(
                f"Resuming after {state['last_processed_date']}: "
                f"{len(days)} days remaining"
            )

    if not days:
        logger.info("No days to process.")
        return

    total_slots = sum(d['rainy_slot_count'] for d in days)
    logger.info(
        f"{'[DRY RUN] ' if args.dry_run else ''}"
        f"Processing {len(days)} days, {total_slots} slots"
    )
    logger.info("=" * 60)

    s3 = get_s3_client()
    state = load_state() if args.resume else {
        "last_processed_date": None, "days_completed": 0
    }
    all_stats = []
    total_start = time.time()

    for i, day_info in enumerate(days):
        day_start = time.time()
        logger.info(
            f"\n[{i+1}/{len(days)}] 📅 {day_info['date']} "
            f"({day_info['rainy_slot_count']} slots, "
            f"{day_info['total_rainfall_mm']:.1f}mm total rainfall)"
        )

        day_stats = process_day(s3, day_info, dry_run=args.dry_run)
        day_stats["day_elapsed_s"] = round(time.time() - day_start, 1)
        all_stats.append(day_stats)

        # 日汇总
        logger.info(
            f"  ✅ {day_info['date']}: "
            f"processed={day_stats['slots_processed']} "
            f"skipped={day_stats['slots_skipped']} "
            f"no_raw={day_stats['slots_no_raw']} "
            f"failed={day_stats['slots_failed']} "
            f"time={day_stats['day_elapsed_s']:.1f}s"
        )

        # 更新进度（非 dry-run）
        if not args.dry_run:
            state['last_processed_date'] = day_info['date']
            state['days_completed'] += 1
            save_state(state)

        # 进度估算
        elapsed_so_far = time.time() - total_start
        remaining_days = len(days) - (i + 1)
        if i > 0:
            avg_per_day = elapsed_so_far / (i + 1)
            eta_s = avg_per_day * remaining_days
            logger.info(
                f"  ⏱️  ETA: ~{eta_s/60:.0f}min "
                f"({remaining_days} days remaining)"
            )

    total_elapsed = time.time() - total_start

    # 生成报告
    report = generate_report(all_stats, total_elapsed, args.dry_run)

    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_FILE, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(f"\n{'=' * 60}")
    logger.info(f"📊 REPORT GENERATED: {REPORT_FILE}")
    logger.info(f"   Days: {report['summary']['total_days']}")
    logger.info(f"   Processed: {report['summary']['total_slots_processed']} slots")
    logger.info(f"   Skipped: {report['summary']['total_slots_skipped']} slots")
    logger.info(f"   Failed: {report['summary']['total_slots_failed']} slots")
    logger.info(f"   Download: {report['summary']['total_download_gb']:.2f} GB")
    logger.info(f"   Total time: {report['summary']['total_time_minutes']:.1f} min")
    logger.info(f"{'=' * 60}")


if __name__ == "__main__":
    main()
