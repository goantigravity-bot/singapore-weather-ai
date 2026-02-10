# 本地测试环境设置指南

本文档说明如何在本地开发环境中设置和运行新加坡天气 AI 应用。

## 📋 系统要求

- **操作系统**: macOS / Linux / Windows (推荐 macOS 或 Linux)
- **Python**: 3.10 或更高版本
- **Node.js**: 18.x 或更高版本
- **内存**: 至少 4GB RAM (推荐 8GB)
- **磁盘空间**: 至少 2GB 可用空间

## 🚀 快速启动

### 一键启动（推荐）

```bash
# 在项目根目录运行
./run-local.sh
```

此脚本会自动完成以下操作：
- ✅ 检查并创建 Python 虚拟环境
- ✅ 安装后端依赖（包括 PyTorch CPU 版本）
- ✅ 安装前端依赖
- ✅ 启动后端服务（端口 8000）
- ✅ 启动前端服务（端口 5173）

### 访问应用

启动成功后，可以通过以下地址访问：

- **前端界面**: http://localhost:5173
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs (Swagger UI)

### 停止服务

```bash
# 方式 1: 使用停止脚本
./stop-local.sh

# 方式 2: 手动停止进程
pkill -f 'uvicorn api:app' && pkill -f 'vite'
```

---

## 🔧 手动设置（详细步骤）

如果需要更精细的控制，可以按照以下步骤手动设置环境。

### 1. 后端设置

#### 1.1 创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 或
venv\Scripts\activate  # Windows
```

#### 1.2 安装依赖

```bash
# 安装基础依赖
pip install -r requirements.txt

# 安装 PyTorch (CPU 版本)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

额外依赖说明：
- `torch`: 深度学习框架，用于模型训练和预测
- `fastapi` + `uvicorn`: API 服务框架
- `pandas` + `numpy`: 数据处理
- `xarray` + `netCDF4`: 卫星数据处理
- `boto3`: AWS S3 集成

#### 1.3 环境变量配置（可选）

如果需要使用邮件通知或访问 JAXA 卫星数据，需要配置环境变量：

```bash
# 复制模板文件
cp env.sh.template env.sh

# 编辑 env.sh 填入实际值
# export SENDER_EMAIL="your-email@gmail.com"
# export SENDER_PASSWORD="your-gmail-app-password"
# export RECIPIENT_EMAIL="recipient@example.com"

# 加载环境变量
source env.sh
```

#### 1.4 启动后端服务

```bash
source venv/bin/activate
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

后端服务会在 http://localhost:8000 启动，日志会输出到终端。

### 2. 前端设置

#### 2.1 安装依赖

```bash
cd frontend
npm install
```

主要依赖：
- `react` + `react-dom`: UI 框架
- `react-router-dom`: 路由管理
- `leaflet` + `react-leaflet`: 地图组件
- `axios`: HTTP 客户端
- `vite`: 构建工具

#### 2.2 启动前端服务

```bash
npm run dev
```

前端开发服务器会在 http://localhost:5173 启动。

### 3. 验证环境

#### 3.1 检查后端健康状态

```bash
curl http://localhost:8000/health
```

预期输出：
```json
{
  "status": "healthy",
  "version": "0.5"
}
```

#### 3.2 测试 API 端点

访问 http://localhost:8000/docs 查看完整的 API 文档并进行测试。

主要端点：
- `GET /health` - 健康检查
- `GET /api/latest` - 获取最新预测数据
- `POST /api/smart-query` - 智能查询功能
- `GET /api/settings` - 获取应用配置
- `GET /monitor/training-history` - 训练历史

#### 3.3 测试前端

在浏览器中打开 http://localhost:5173，应该能看到：
- 🗺️ 新加坡地图
- 📊 PM2.5 预测数据
- 🔍 智能查询搜索框

---

## 📂 项目结构

```
claude-skill/
├── frontend/               # React 前端应用
│   ├── src/
│   │   ├── App.tsx        # 主应用组件
│   │   ├── components/    # UI 组件
│   │   └── ...
│   └── package.json       # 前端依赖配置
├── api.py                 # FastAPI 后端服务
├── predict.py             # 预测逻辑
├── smart_query.py         # 智能查询 (NLU)
├── requirements.txt       # Python 依赖
├── run-local.sh          # 一键启动脚本
├── stop-local.sh         # 停止服务脚本
└── weather.db            # SQLite 数据库
```

---

## 🧪 运行测试

### 后端测试

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行测试
pytest

# 运行特定测试
pytest test_api.py
pytest test_auto_training.py
```

### 前端测试

```bash
cd frontend

# 运行测试
npm run test

# 运行测试并生成覆盖率报告
npm run coverage
```

---

## 🐛 常见问题

### 问题 1: `venv` 创建失败

**症状**: `python3 -m venv venv` 失败

**解决方案**:
```bash
# macOS
brew install python@3.10

# Ubuntu
sudo apt install python3.10-venv
```

### 问题 2: PyTorch 安装缓慢

**症状**: `pip install torch` 下载很慢

**解决方案**: 使用清华镜像源
```bash
pip install torch torchvision -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 问题 3: 端口已被占用

**症状**: `Address already in use: 0.0.0.0:8000`

**解决方案**:
```bash
# 查找占用端口的进程
lsof -i :8000
lsof -i :5173

# 终止进程
kill -9 <PID>
```

### 问题 4: 前端无法连接后端

**症状**: 前端请求失败，CORS 错误

**解决方案**: 
1. 确保后端服务正在运行 (`curl http://localhost:8000/health`)
2. 检查前端配置中的 API 地址是否正确
3. 后端已配置 CORS，允许本地开发访问

### 问题 5: `npm install` 卡住

**症状**: `npm install` 长时间没有响应

**解决方案**:
```bash
# 清除缓存
npm cache clean --force

# 使用淘宝镜像
npm config set registry https://registry.npmmirror.com

# 重新安装
npm install
```

---

## 📝 开发日志

应用运行时会生成以下日志文件：

- `backend.log` - 后端服务日志
- `frontend-local.log` - 前端开发服务器日志
- `api.log` - API 请求日志

查看实时日志：
```bash
# 后端日志
tail -f backend.log

# API 日志
tail -f api.log
```

---

## 🔄 开发工作流

### 典型开发流程

1. **启动服务**
   ```bash
   ./run-local.sh
   ```

2. **修改代码**
   - 后端代码会自动重载（`--reload` 选项）
   - 前端代码会热更新（HMR）

3. **测试修改**
   - 在浏览器中验证前端变化
   - 在 http://localhost:8000/docs 测试 API

4. **提交代码**
   ```bash
   git add .
   git commit -m "描述: 你的修改内容"
   git push
   ```

5. **停止服务**
   ```bash
   ./stop-local.sh
   ```

### 仅启动后端

如果只需要测试 API：

```bash
source venv/bin/activate
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

### 仅启动前端

如果后端已在运行（或使用远程后端）：

```bash
cd frontend
npm run dev
```

---

## 🎯 下一步

本地环境设置完成后，你可以：

1. **探索功能**: 
   - 查看实时 PM2.5 预测地图
   - 尝试智能查询功能
   - 查看训练监控面板 (http://localhost:8000/monitor/training-history)

2. **开发新功能**:
   - 参考 `docs/` 目录下的需求文档
   - 查看 `CHANGELOG.md` 了解版本历史

3. **部署到云端**:
   - 参考 `AWS_DEPLOYMENT_GUIDE.md` 进行 AWS 部署
   - 参考 `CLOUD_DEPLOYMENT_GUIDE.md` 了解完整部署流程

---

## 📚 相关文档

- [项目概述](PROJECT_SUMMARY.md) - 项目整体说明
- [AWS 部署指南](AWS_DEPLOYMENT_GUIDE.md) - 云端部署步骤
- [自动训练说明](AUTO_TRAINING_README.md) - 模型训练流程
- [API 文档](http://localhost:8000/docs) - 完整 API 参考

---

## 💡 提示

- 🔥 **热重载**: 代码修改后会自动生效，无需重启
- 📊 **监控**: 访问 `/monitor/training-history` 查看训练状态
- 🐛 **调试**: 使用浏览器开发者工具查看网络请求和控制台日志
- 💾 **数据库**: 本地使用 SQLite (`weather.db`)，生产环境使用 PostgreSQL

---

**最后更新**: 2026-02-08  
**版本**: 0.5
