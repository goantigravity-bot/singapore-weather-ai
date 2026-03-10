# Tomorrow Tasks (2026-02-18)

## 进行中 (后台)

- [ ] 🔄 下载服务器运行中 — 预计 ~02-20 完成
  - 12 workers, ProcessPoolExecutor, hsd_parser
  - 当前 ~224 文件/分, S3 已有 ~51K 文件, 第 121/2239 天
  - 检查日志: `ssh ubuntu@47.129.209.156 "tail -5 /home/ubuntu/download/download.log"`

---

## 优先级 1: 预测精度仪表盘 (~1天)

用 `forecast_result` + `actual_result` 表做预测 vs 实际对比，直观展示模型准确率。

- [ ] 查询数据库中已有的 forecast/actual 数据量
- [ ] 后端 API: `/api/accuracy` 返回按天/小时聚合的准确率指标 (MAE, 命中率)
- [ ] 前端: 趋势图组件 (Chart.js / Recharts)
- [ ] 集成到现有 Monitor 页面或新建 Accuracy 页

## 优先级 2: 雨量预警推送 (~半天)

当预测降雨概率 > 阈值时主动通知用户。

- [x] Telegram Bot 集成 (@WeatherAIAlertBot)
- [x] API 端点: `/telegram/status`, `/test`, `/alert`
- [x] 部署到 API 服务器并验证
- [ ] 定时任务: 每 10 分钟检查预测结果并自动推送
- [ ] 可配置: 地点、阈值、通知频率
- [ ] 前端: 设置页面添加 Telegram 绑定入口

## 优先级 3: 自然语言查询 (~2天)

"明天去东海岸跑步会下雨吗？" → 结构化预测 → 自然语言回答。

- [ ] Gemini API 集成 (intent parsing)
- [ ] `/api/chat` 端点
- [ ] 前端: Chat bubble 组件

## 优先级 4: 多时段预测 (~1天)

扩展预测范围：10min → 30min/1h/3h。

- [ ] 模型输出层调整 (多 head 或多次推理)
- [ ] API 支持 `horizon` 参数
- [ ] 前端: 时间线/趋势图展示

## 优先级 5: PWA 离线支持 (~半天)

- [ ] Service Worker + manifest.json
- [ ] 缓存最近预测结果
- [ ] 可安装到手机桌面

---

## 数据下载完成后 (~02-20)

- [ ] 用 2020-2026 六年数据重训模型
- [ ] 模型架构升级 (Attention, 多尺度)
- [ ] 多城市扩展 (KL, Jakarta)
