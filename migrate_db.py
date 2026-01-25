#!/usr/bin/env python3
"""
数据库迁移脚本：为 search_history 表添加 ip_address 字段
"""
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """为现有数据库添加 ip_address 列"""
    try:
        conn = sqlite3.connect('weather.db')
        c = conn.cursor()
        
        # 检查列是否已存在
        c.execute("PRAGMA table_info(search_history)")
        columns = [column[1] for column in c.fetchall()]
        
        if 'ip_address' not in columns:
            logger.info("添加 ip_address 列到 search_history 表...")
            c.execute("ALTER TABLE search_history ADD COLUMN ip_address TEXT")
            conn.commit()
            logger.info("✅ 迁移成功完成")
        else:
            logger.info("✅ ip_address 列已存在，无需迁移")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        raise

if __name__ == "__main__":
    migrate_database()
