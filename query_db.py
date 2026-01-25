#!/usr/bin/env python3
"""
数据库查询工具
用法：python3 query_db.py
"""
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

def connect_db():
    """连接数据库"""
    return sqlite3.connect('weather.db')

def show_recent_searches(limit=20):
    """显示最近的搜索记录"""
    conn = connect_db()
    query = f"""
        SELECT id, query, ip_address, timestamp 
        FROM search_history 
        ORDER BY timestamp DESC 
        LIMIT {limit}
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    print(f"\n📊 最近 {limit} 条搜索记录:")
    print("=" * 80)
    print(df.to_string(index=False))
    print()

def show_popular_searches(limit=10):
    """显示热门搜索"""
    conn = connect_db()
    query = f"""
        SELECT query, COUNT(*) as count 
        FROM search_history 
        GROUP BY query 
        ORDER BY count DESC 
        LIMIT {limit}
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    print(f"\n🔥 热门搜索 TOP {limit}:")
    print("=" * 80)
    print(df.to_string(index=False))
    print()

def show_ip_stats():
    """显示IP统计"""
    conn = connect_db()
    query = """
        SELECT ip_address, COUNT(*) as search_count 
        FROM search_history 
        WHERE ip_address IS NOT NULL
        GROUP BY ip_address 
        ORDER BY search_count DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    print("\n🌐 IP地址统计:")
    print("=" * 80)
    print(df.to_string(index=False))
    print()

def show_today_stats():
    """显示今日统计"""
    conn = connect_db()
    today = datetime.now().date()
    query = f"""
        SELECT COUNT(*) as total_searches,
               COUNT(DISTINCT ip_address) as unique_ips,
               COUNT(DISTINCT query) as unique_queries
        FROM search_history 
        WHERE DATE(timestamp) = '{today}'
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    print(f"\n📅 今日统计 ({today}):")
    print("=" * 80)
    print(f"总搜索次数: {df['total_searches'][0]}")
    print(f"独立IP数: {df['unique_ips'][0]}")
    print(f"独立查询数: {df['unique_queries'][0]}")
    print()

def custom_query(sql):
    """执行自定义SQL查询"""
    conn = connect_db()
    try:
        df = pd.read_sql_query(sql, conn)
        print("\n🔍 查询结果:")
        print("=" * 80)
        print(df.to_string(index=False))
        print()
    except Exception as e:
        print(f"❌ 查询错误: {e}")
    finally:
        conn.close()

def main():
    """主菜单"""
    while True:
        print("\n" + "=" * 80)
        print("🗄️  Weather DB 查询工具")
        print("=" * 80)
        print("1. 查看最近搜索记录")
        print("2. 查看热门搜索")
        print("3. 查看IP统计")
        print("4. 查看今日统计")
        print("5. 执行自定义SQL")
        print("0. 退出")
        print("=" * 80)
        
        choice = input("\n请选择 (0-5): ").strip()
        
        if choice == "1":
            limit = input("显示多少条? (默认20): ").strip()
            limit = int(limit) if limit.isdigit() else 20
            show_recent_searches(limit)
        elif choice == "2":
            show_popular_searches()
        elif choice == "3":
            show_ip_stats()
        elif choice == "4":
            show_today_stats()
        elif choice == "5":
            sql = input("输入SQL查询: ").strip()
            if sql:
                custom_query(sql)
        elif choice == "0":
            print("\n👋 再见！")
            break
        else:
            print("❌ 无效选择，请重试")

if __name__ == "__main__":
    main()
