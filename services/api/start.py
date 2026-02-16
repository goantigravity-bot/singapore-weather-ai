#!/usr/bin/env python3
"""
API 服务器启动入口。

WorkingDirectory 保持在 services/api/（数据文件所在路径），
通过 sys.path 让 Python 找到 backend/ 下的模块。
"""
import sys
import os

# 将 backend/ 加入 Python 模块搜索路径
backend_dir = os.path.join(os.path.dirname(__file__), "backend")
sys.path.insert(0, backend_dir)

# 启动 FastAPI 应用
from api import app  # noqa: E402

if __name__ == "__main__":
    import uvicorn
    workers = 2
    for i, arg in enumerate(sys.argv):
        if arg == "--workers" and i + 1 < len(sys.argv):
            workers = int(sys.argv[i + 1])
    uvicorn.run("start:app", host="0.0.0.0", port=8000, workers=workers)
