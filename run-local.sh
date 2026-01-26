#!/bin/bash
# 本地运行新加坡天气 AI 应用

set -e

echo "🚀 启动新加坡天气 AI 应用（本地开发模式）"
echo "=================================================="

# 检查是否在正确的目录
if [ ! -f "api.py" ]; then
    echo "❌ 错误：请在项目根目录运行此脚本"
    exit 1
fi

# 检查 Python 依赖
echo ""
echo "📦 检查后端依赖..."
if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "安装 Python 依赖..."
pip install -q fastapi uvicorn httpx python-dotenv pydantic

# 检查前端依赖
echo ""
echo "📦 检查前端依赖..."
cd frontend
if [ ! -d "node_modules" ]; then
    echo "安装 npm 依赖..."
    npm install
fi
cd ..

echo ""
echo "=================================================="
echo "✅ 依赖检查完成！"
echo "=================================================="
echo ""
echo "启动服务..."
echo ""

# 在后台启动后端
echo "🔧 启动后端服务 (http://localhost:8000)..."
source venv/bin/activate
uvicorn api:app --host 0.0.0.0 --port 8000 --reload > backend.log 2>&1 &
BACKEND_PID=$!
echo "后端 PID: $BACKEND_PID"

# 等待后端启动
echo "等待后端启动..."
sleep 3

# 检查后端是否运行
if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ 后端启动成功！"
else
    echo "❌ 后端启动失败，请检查 backend.log"
    kill $BACKEND_PID 2>/dev/null || true
    exit 1
fi

# 启动前端
echo ""
echo "🎨 启动前端服务 (http://localhost:5173)..."
cd frontend
npm run dev > ../frontend-local.log 2>&1 &
FRONTEND_PID=$!
echo "前端 PID: $FRONTEND_PID"
cd ..

echo ""
echo "=================================================="
echo "🎉 应用启动成功！"
echo "=================================================="
echo ""
echo "📍 访问地址:"
echo "   前端: http://localhost:5173"
echo "   后端: http://localhost:8000"
echo "   API 文档: http://localhost:8000/docs"
echo ""
echo "📝 日志文件:"
echo "   后端: backend.log"
echo "   前端: frontend-local.log"
echo ""
echo "🛑 停止服务:"
echo "   kill $BACKEND_PID $FRONTEND_PID"
echo ""
echo "或者运行: pkill -f 'uvicorn api:app' && pkill -f 'vite'"
echo ""
echo "=================================================="

# 保存 PID 到文件
echo "$BACKEND_PID" > .backend.pid
echo "$FRONTEND_PID" > .frontend.pid

echo ""
echo "按 Ctrl+C 可以查看日志，但服务会继续在后台运行"
echo "使用上面的命令停止服务"
