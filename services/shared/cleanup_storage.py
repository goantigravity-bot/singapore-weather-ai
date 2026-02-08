#!/usr/bin/env python3
"""
存储优化脚本
自动清理旧的卫星数据和日志文件，防止存储空间无限增长
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
import logging

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 配置参数
SATELLITE_DATA_DIR = "satellite_data"
PROCESSED_DATA_DIR = "processed_data"
TRAINING_LOGS_DIR = "training_logs"
TRAINING_REPORTS_DIR = "training_reports"

# 保留天数配置
KEEP_RAW_SATELLITE_DAYS = 1      # 原始卫星数据保留1天
KEEP_PROCESSED_DATA_DAYS = 30    # 预处理数据保留30天
KEEP_TRAINING_LOGS_DAYS = 30     # 训练日志保留30天
KEEP_TRAINING_REPORTS = 10       # 训练报告保留最近10个


def get_file_age_days(file_path):
    """获取文件年龄（天数）"""
    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
    age = datetime.now() - file_time
    return age.days


def cleanup_old_files(directory, pattern, days_to_keep):
    """
    清理旧文件
    
    Args:
        directory: 目录路径
        pattern: 文件模式（如 "*.nc"）
        days_to_keep: 保留天数
    
    Returns:
        删除的文件数量和释放的空间（字节）
    """
    if not os.path.exists(directory):
        logger.warning(f"目录不存在: {directory}")
        return 0, 0
    
    deleted_count = 0
    freed_space = 0
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    logger.info(f"清理 {directory} 中 {days_to_keep} 天前的 {pattern} 文件...")
    
    for file in Path(directory).glob(pattern):
        if file.is_file():
            file_time = datetime.fromtimestamp(file.stat().st_mtime)
            
            if file_time < cutoff_date:
                file_size = file.stat().st_size
                try:
                    file.unlink()
                    deleted_count += 1
                    freed_space += file_size
                    logger.info(f"  已删除: {file.name} ({file_size / 1024 / 1024:.2f} MB)")
                except Exception as e:
                    logger.error(f"  删除失败 {file.name}: {e}")
    
    return deleted_count, freed_space


def cleanup_old_reports(directory, keep_count):
    """
    清理旧的训练报告，只保留最近N个
    
    Args:
        directory: 报告目录
        keep_count: 保留数量
    
    Returns:
        删除的文件数量和释放的空间（字节）
    """
    if not os.path.exists(directory):
        logger.warning(f"目录不存在: {directory}")
        return 0, 0
    
    deleted_count = 0
    freed_space = 0
    
    # 获取所有报告文件，按修改时间排序
    reports = list(Path(directory).glob("report_*.html"))
    reports.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    # 删除超出保留数量的文件
    if len(reports) > keep_count:
        logger.info(f"清理旧的训练报告（保留最近 {keep_count} 个）...")
        
        for report in reports[keep_count:]:
            file_size = report.stat().st_size
            try:
                report.unlink()
                deleted_count += 1
                freed_space += file_size
                logger.info(f"  已删除: {report.name}")
            except Exception as e:
                logger.error(f"  删除失败 {report.name}: {e}")
    
    return deleted_count, freed_space


def get_directory_size(directory):
    """获取目录大小（字节）"""
    if not os.path.exists(directory):
        return 0
    
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if os.path.exists(filepath):
                total_size += os.path.getsize(filepath)
    
    return total_size


def format_bytes(bytes_size):
    """格式化字节大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


def print_storage_summary():
    """打印存储使用摘要"""
    logger.info("\n" + "="*60)
    logger.info("存储使用摘要")
    logger.info("="*60)
    
    directories = [
        (SATELLITE_DATA_DIR, "原始卫星数据"),
        (PROCESSED_DATA_DIR, "预处理数据"),
        (TRAINING_LOGS_DIR, "训练日志"),
        (TRAINING_REPORTS_DIR, "训练报告")
    ]
    
    total_size = 0
    for dir_path, dir_name in directories:
        size = get_directory_size(dir_path)
        total_size += size
        logger.info(f"{dir_name:20s}: {format_bytes(size)}")
    
    logger.info("-"*60)
    logger.info(f"{'总计':20s}: {format_bytes(total_size)}")
    logger.info("="*60 + "\n")


def main():
    """主函数"""
    logger.info("🧹 开始存储清理...")
    
    # 打印清理前的存储摘要
    print_storage_summary()
    
    total_deleted = 0
    total_freed = 0
    
    # 1. 清理原始卫星数据（.nc文件）
    count, space = cleanup_old_files(
        SATELLITE_DATA_DIR,
        "*.nc",
        KEEP_RAW_SATELLITE_DAYS
    )
    total_deleted += count
    total_freed += space
    
    # 2. 清理旧的预处理数据（.npy文件）
    count, space = cleanup_old_files(
        PROCESSED_DATA_DIR,
        "*.npy",
        KEEP_PROCESSED_DATA_DAYS
    )
    total_deleted += count
    total_freed += space
    
    # 3. 清理旧的训练日志
    count, space = cleanup_old_files(
        TRAINING_LOGS_DIR,
        "*.log",
        KEEP_TRAINING_LOGS_DAYS
    )
    total_deleted += count
    total_freed += space
    
    # 4. 清理旧的训练报告
    count, space = cleanup_old_reports(
        TRAINING_REPORTS_DIR,
        KEEP_TRAINING_REPORTS
    )
    total_deleted += count
    total_freed += space
    
    # 打印清理结果
    logger.info("\n" + "="*60)
    logger.info("清理完成")
    logger.info("="*60)
    logger.info(f"删除文件数: {total_deleted}")
    logger.info(f"释放空间: {format_bytes(total_freed)}")
    logger.info("="*60 + "\n")
    
    # 打印清理后的存储摘要
    print_storage_summary()
    
    logger.info("✅ 存储清理完成！")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"清理失败: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
