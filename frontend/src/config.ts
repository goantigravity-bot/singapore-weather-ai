
// API 配置 - 从环境变量读取
// 生产环境使用 .env.production 中配置的后端 URL
export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
