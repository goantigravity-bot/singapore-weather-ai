#!/usr/bin/env python3
"""
Unit tests for db.py — Weather AI data storage schema.
Tests table creation, data insertion, deduplication, and FK relationships.
"""
import os
import sys
import sqlite3
import unittest

# 使用独立的测试 DB
TEST_DB = "weather_test.db"

# 在 import db 之前设置 DB_PATH
sys.path.insert(0, os.path.dirname(__file__))
import db as weather_db
weather_db.DB_PATH = TEST_DB


class TestDatabaseSchema(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """创建测试数据库"""
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        weather_db.create_tables()

    @classmethod
    def tearDownClass(cls):
        """清理测试数据库"""
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def _query(self, sql, params=()):
        conn = sqlite3.connect(TEST_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        return rows

    # ── Table Creation ──

    def test_01_tables_exist(self):
        """验证所有 6 张表都已创建"""
        rows = self._query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        table_names = {r["name"] for r in rows}
        expected = {"user_activity", "place", "location", "activity", "forecast_result", "actual_result"}
        self.assertTrue(expected.issubset(table_names), f"Missing tables: {expected - table_names}")

    def test_02_indexes_exist(self):
        """验证查询优化索引已创建"""
        rows = self._query("SELECT name FROM sqlite_master WHERE type='index'")
        idx_names = {r["name"] for r in rows}
        expected_indexes = {
            "idx_location_place", "idx_forecast_query",
            "idx_forecast_loc", "idx_actual_loc", "idx_actual_time"
        }
        self.assertTrue(expected_indexes.issubset(idx_names), f"Missing indexes: {expected_indexes - idx_names}")

    # ── user_activity ──

    def test_10_save_user_activity(self):
        """保存用户查询记录"""
        qid = weather_db.save_user_activity(
            query="ride bicycle at rail corridor 2 to 5pm",
            response_time_ms=1234.5,
            forecast_outcome="NOT RECOMMENDED",
            ip_address="192.168.1.1"
        )
        self.assertIsNotNone(qid)
        self.assertGreater(qid, 0)

        rows = self._query("SELECT * FROM user_activity WHERE query_id = ?", (qid,))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["query"], "ride bicycle at rail corridor 2 to 5pm")
        self.assertEqual(rows[0]["forecast_outcome"], "NOT RECOMMENDED")
        self.assertAlmostEqual(rows[0]["response_time_ms"], 1234.5, places=1)

    # ── place ──

    def test_20_get_or_create_place_new(self):
        """创建新地点"""
        pid = weather_db.get_or_create_place(
            place_name="Rail Corridor", place_type="path",
            center_lat=1.3521, center_lon=103.8198
        )
        self.assertIsNotNone(pid)

        rows = self._query("SELECT * FROM place WHERE place_id = ?", (pid,))
        self.assertEqual(rows[0]["place_name"], "Rail Corridor")
        self.assertEqual(rows[0]["place_type"], "path")

    def test_21_get_or_create_place_existing(self):
        """重复创建同名地点应返回已有 ID"""
        pid1 = weather_db.get_or_create_place("Sentosa", "point", 1.25, 103.82)
        pid2 = weather_db.get_or_create_place("Sentosa", "point", 1.25, 103.82)
        self.assertEqual(pid1, pid2)

    # ── location ──

    def test_30_save_locations(self):
        """保存路径上的多个坐标点"""
        pid = weather_db.get_or_create_place("East Coast Park", "path", 1.3, 103.9)
        points = [(1.3001, 103.9001), (1.3002, 103.9002), (1.3003, 103.9003)]
        loc_ids = weather_db.save_locations_for_place(pid, points)

        self.assertEqual(len(loc_ids), 3)

        rows = self._query("SELECT * FROM location WHERE place_id = ? ORDER BY point_index", (pid,))
        self.assertEqual(len(rows), 3)
        self.assertAlmostEqual(rows[0]["lat"], 1.3001, places=4)

    def test_31_save_locations_no_duplicate(self):
        """同一 place 下相同坐标不重复插入"""
        pid = weather_db.get_or_create_place("East Coast Park")
        loc_ids_1 = weather_db.save_locations_for_place(pid, [(1.3001, 103.9001)])
        loc_ids_2 = weather_db.save_locations_for_place(pid, [(1.3001, 103.9001)])
        self.assertEqual(loc_ids_1[0], loc_ids_2[0])

    # ── activity ──

    def test_40_save_activity(self):
        """保存活动记录"""
        qid = weather_db.save_user_activity("walk at sentosa", 500.0, "GO AHEAD")
        aid = weather_db.save_activity(qid, "Walking", 0.2)
        self.assertIsNotNone(aid)

        rows = self._query("SELECT * FROM activity WHERE activity_id = ?", (aid,))
        self.assertEqual(rows[0]["activity_name"], "Walking")
        self.assertAlmostEqual(rows[0]["rain_tolerance"], 0.2, places=1)
        self.assertEqual(rows[0]["query_id"], qid)

    # ── forecast_result ──

    def test_50_save_forecast_results(self):
        """批量保存预测结果"""
        qid = weather_db.save_user_activity("test forecast", 300.0, "CAUTION ADVISED")
        pid = weather_db.get_or_create_place("Test Place", "point", 1.35, 103.8)
        loc_ids = weather_db.save_locations_for_place(pid, [(1.35, 103.8)])

        weather_db.save_forecast_results(qid, [
            {
                "loc_id": loc_ids[0],
                "rainfall_mm": 1.5,
                "status": "Light Rain",
                "confidence": 0.7,
                "is_risky": True,
                "response_time_ms": 150.0,
                "forecast_time": "2026-02-12T22:00:00",
            }
        ])

        rows = self._query("SELECT * FROM forecast_result WHERE query_id = ?", (qid,))
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["rainfall_mm"], 1.5, places=1)
        self.assertEqual(rows[0]["status"], "Light Rain")
        self.assertEqual(rows[0]["is_risky"], 1)

    # ── actual_result ──

    def test_60_save_actual_result(self):
        """保存实际观测结果"""
        pid = weather_db.get_or_create_place("Actual Test", "point", 1.3, 103.8)
        loc_ids = weather_db.save_locations_for_place(pid, [(1.3, 103.8)])

        aid = weather_db.save_actual_result(
            loc_id=loc_ids[0],
            actual_rainfall_mm=2.3,
            observation_time="2026-02-12T22:10:00",
            source="NEA"
        )
        self.assertIsNotNone(aid)

        rows = self._query("SELECT * FROM actual_result WHERE actual_id = ?", (aid,))
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["actual_rainfall_mm"], 2.3, places=1)
        self.assertEqual(rows[0]["source"], "NEA")

    # ── End-to-End Flow ──

    def test_90_full_smart_query_flow(self):
        """模拟 smart-query 的完整数据写入流"""
        # 1. 保存用户查询
        qid = weather_db.save_user_activity(
            query="ride bicycle at rail corridor 2 to 5pm",
            response_time_ms=2500.0,
            forecast_outcome="NOT RECOMMENDED",
            ip_address="10.0.0.1"
        )

        # 2. 保存活动
        weather_db.save_activity(qid, "Cycling", 0.5)

        # 3. 保存地点 + 15 个路径点
        pid = weather_db.get_or_create_place("rail corridor", "path", 1.34, 103.78)
        points = [(1.34 + i * 0.001, 103.78 + i * 0.001) for i in range(15)]
        loc_ids = weather_db.save_locations_for_place(pid, points)
        self.assertEqual(len(loc_ids), 15)

        # 4. 保存 15 个预测结果
        forecasts = []
        for i, lid in enumerate(loc_ids):
            forecasts.append({
                "loc_id": lid,
                "rainfall_mm": i * 0.3,
                "status": "Heavy Rain" if i * 0.3 > 2.0 else "Light Rain" if i * 0.3 > 0.5 else "Clear",
                "confidence": 0.6,
                "is_risky": i * 0.3 > 0.5,
                "response_time_ms": 100.0,
                "forecast_time": "2026-02-12T14:00:00",
            })
        weather_db.save_forecast_results(qid, forecasts)

        # 5. 验证
        fc_rows = self._query("SELECT * FROM forecast_result WHERE query_id = ?", (qid,))
        self.assertEqual(len(fc_rows), 15)

        # 验证关联：location → place
        loc_rows = self._query("SELECT * FROM location WHERE place_id = ?", (pid,))
        self.assertEqual(len(loc_rows), 15)

        # 验证 activity
        act_rows = self._query("SELECT * FROM activity WHERE query_id = ?", (qid,))
        self.assertEqual(len(act_rows), 1)
        self.assertEqual(act_rows[0]["activity_name"], "Cycling")


if __name__ == "__main__":
    unittest.main(verbosity=2)
