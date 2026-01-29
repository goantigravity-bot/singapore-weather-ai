# 前端测试覆盖率目标

## 当前状态 (2026-01-29)

- **整体覆盖率**: 35.91%
- **测试数量**: 32 个
- **测试通过率**: 100%

---

## TODO 列表

### 高优先级

- [ ] **App.tsx** 集成测试
  - 路由切换测试
  - 地理位置 fallback 测试
  - 搜索功能测试

- [ ] **ForecastPanel.tsx** 测试
  - 加载状态显示
  - 数据渲染测试
  - 错误状态处理

### 中优先级

- [ ] **MapComponent.tsx** 测试
  - 需要 mock Leaflet 库
  - 标记点点击测试
  - 路径绘制测试

- [ ] **SideMenu.tsx** 测试
  - 打开/关闭状态
  - 导航链接

### 低优先级

- [ ] **QuickLinks.tsx** 测试
- [ ] 提升 TrainingMonitor 分支覆盖率（当前 23.65%）

---

## 覆盖率目标

| 阶段 | 目标覆盖率 | 状态 |
|-----|----------|------|
| Phase 1 | 35% | ✅ 已达成 |
| Phase 2 | 50% | ⏳ 待完成 |
| Phase 3 | 70% | ⏳ 待完成 |
| Phase 4 | 80% | ⏳ 待完成 |

---

## 当前覆盖率详情

| 模块 | 语句 | 分支 | 函数 |
|-----|------|------|------|
| ConfigContext.tsx | 95.12% | 90% | 100% |
| AboutPage.tsx | 100% | 100% | 100% |
| SettingsPage.tsx | 77.77% | 50% | 50% |
| StatsPage.tsx | 73.33% | 75% | 57.14% |
| TrainingMonitor.tsx | 63.63% | 23.65% | 38.88% |
| App.tsx | 0% | 0% | 0% |
| MapComponent.tsx | 0% | 0% | 0% |
| ForecastPanel.tsx | 0% | 0% | 0% |

---

## 运行命令

```bash
npm run test        # 交互式测试
npm run test:run    # 单次运行
npm run coverage    # 生成覆盖率报告
```
