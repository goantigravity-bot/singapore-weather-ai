"""
多服务健康检查脚本：定期探测 API、Download、Training 三个服务的状态。

通过 cron 每 5 分钟运行：
*/5 * * * * cd /home/ubuntu/weather-ai/services/api/backend && python3 health_check.py

数据写入 SQLite health_check 表（每个服务一条记录），供 dashboard 展示。
"""
import os
import time
import sqlite3
import logging
import urllib.request
import json
from datetime import datetime, timezone, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_BASE = os.environ.get("API_URL", "http://localhost:8000/api")
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "weather.db"))
SGT = timezone(timedelta(hours=8))


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS health_check (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service TEXT NOT NULL,
            check_time TEXT NOT NULL,
            status TEXT NOT NULL,
            response_time_ms REAL,
            details TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()


def http_get(url, timeout=10):
    """发送 HTTP GET 请求，返回 (status_code, body_dict, elapsed_ms)。"""
    start = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HealthCheck/2.0"})
        resp = urllib.request.urlopen(req, timeout=timeout)
        elapsed_ms = (time.time() - start) * 1000
        body = json.loads(resp.read().decode())
        return resp.status, body, round(elapsed_ms, 1)
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        return None, {"error": str(e)[:200]}, round(elapsed_ms, 1)


def check_api():
    """检查 API 服务是否在线。"""
    code, body, ms = http_get(f"{API_BASE}/health")
    if code == 200 and body.get("status") == "ok":
        return {"service": "api", "status": "ok", "response_time_ms": ms,
                "details": f"v{body.get('version', '?')}"}
    return {"service": "api", "status": "down", "response_time_ms": ms,
            "details": body.get("error", "unhealthy")}


def check_download_and_training():
    """通过 /monitor/overview 获取 Download 和 Training 状态。"""
    results = []
    code, body, ms = http_get(f"{API_BASE}/monitor/overview")

    if code != 200:
        # API 挂了，两个服务都标 unknown
        results.append({"service": "download", "status": "unknown", "response_time_ms": ms,
                        "details": "monitor endpoint unreachable"})
        results.append({"service": "training", "status": "unknown", "response_time_ms": ms,
                        "details": "monitor endpoint unreachable"})
        return results

    # Download 状态
    dl = body.get("download", {})
    dl_status_raw = dl.get("status", "unknown")
    # monitor/overview 返回: sleeping / running / downloading / completed / idle
    if dl_status_raw in ("running", "downloading"):
        dl_status = "running"
    elif dl_status_raw in ("idle", "completed", "stopped", "sleeping"):
        dl_status = "idle"
    else:
        dl_status = "unknown"
    dl_detail = f"status={dl_status_raw}, days={dl.get('completedDays', '?')}, files={dl.get('filesDownloaded', '?')}"
    results.append({"service": "download", "status": dl_status, "response_time_ms": ms,
                    "details": dl_detail})

    # Training 状态
    tr = body.get("training", {})
    tr_status_raw = tr.get("status", "unknown")
    # monitor/overview 返回: waiting / training / running / completed / idle
    if tr_status_raw in ("training", "running"):
        tr_status = "running"
    elif tr_status_raw in ("idle", "completed", "waiting"):
        tr_status = "idle"
    else:
        tr_status = "unknown"
    tr_detail = f"status={tr_status_raw}, phase={tr.get('currentPhase', '?')}"
    results.append({"service": "training", "status": tr_status, "response_time_ms": ms,
                    "details": tr_detail})

    return results


def save_results(results):
    """将所有服务检查结果写入 SQLite。"""
    now_sgt = datetime.now(SGT).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    for r in results:
        conn.execute(
            "INSERT INTO health_check (service, check_time, status, response_time_ms, details) VALUES (?,?,?,?,?)",
            (r["service"], now_sgt, r["status"], r.get("response_time_ms"), r.get("details"))
        )
    conn.commit()

    # 保留 30 天数据
    conn.execute("DELETE FROM health_check WHERE created_at < datetime('now', '-30 days')")
    conn.commit()
    conn.close()


def main():
    results = []

    # 1. API 健康检查
    results.append(check_api())

    # 2. Download + Training（通过 monitor/overview）
    results.extend(check_download_and_training())

    # 3. 保存
    save_results(results)

    # 4. 日志输出
    icons = {"ok": "🟢", "running": "🔵", "idle": "⚪", "down": "🔴", "unknown": "⚫"}
    for r in results:
        icon = icons.get(r["status"], "⚫")
        logger.info(f"  {icon} {r['service']:<10} {r['status']:<8} {r.get('response_time_ms', 0):>6.1f}ms  {r.get('details', '')}")


if __name__ == "__main__":
    main()
