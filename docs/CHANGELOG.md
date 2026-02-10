# 新加坡天气 AI 应用 - 版本历史

## v0.5 (2026-01-26)

### 🚀 新功能
- AWS 生产环境部署
  - 前端部署到 S3 静态网站托管
  - 后端部署到 EC2 (Ubuntu 22.04)
  - Nginx 反向代理配置
  - systemd 服务管理

### 🔧 改进
- 本地开发环境优化
  - 创建自动化启动脚本 (`run-local.sh`)
  - 创建自动化停止脚本 (`stop-local.sh`)
  - 环境配置分离（`.env.local` 和 `.env.production`）

### 🐛 修复
- 修复 CORS 头部重复问题
  - 移除 Nginx CORS 配置
  - 统一由 FastAPI CORSMiddleware 处理
- 解决 Mixed Content 问题
  - 使用 S3 HTTP 端点而非 CloudFront HTTPS

### 📝 文档
- 添加部署脚本和文档
  - `deploy-backend.sh` - 后端部署脚本
  - `deploy-frontend.sh` - 前端部署脚本
  - `fix-cors.sh` - CORS 修复脚本
- 创建完整的部署验证报告

### 🌐 部署地址
- **生产环境前端**: http://weather-ai-frontend-jinhui-20260126.s3-website-ap-southeast-1.amazonaws.com
- **生产环境后端**: http://3.0.28.161
- **本地开发前端**: http://localhost:5173
- **本地开发后端**: http://localhost:8000

---

## v0.4 (之前版本)

### 功能
- 交互式地图界面（Leaflet）
- 天气站标记显示
- 地点搜索功能
- 天气预报显示
- 搜索统计页面
- React + TypeScript 前端
- FastAPI Python 后端
