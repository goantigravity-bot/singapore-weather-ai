#!/bin/bash
# 停止本地运行的服务

echo "🛑 停止本地服务..."

# 从 PID 文件停止
if [ -f ".backend.pid" ]; then
    BACKEND_PID=$(cat .backend.pid)
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo "停止后端服务 (PID: $BACKEND_PID)..."
        kill $BACKEND_PID
    fi
    rm .backend.pid
fi

if [ -f ".frontend.pid" ]; then
    FRONTEND_PID=$(cat .frontend.pid)
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "停止前端服务 (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID
    fi
    rm .frontend.pid
fi

# 确保所有进程都停止
pkill -f 'uvicorn api:app' 2>/dev/null || true
pkill -f 'vite' 2>/dev/null || true

echo "✅ 服务已停止"
