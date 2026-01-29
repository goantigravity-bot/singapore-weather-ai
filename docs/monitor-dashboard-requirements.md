# 监控仪表盘 UI 需求规格

## 概述
训练监控仪表盘 (`/training`) 提供端到端流程的可视化监控，包括文件下载、模型训练和 API 同步三个阶段。

---

## 1. 页面布局

### 1.1 全宽页面布局
- **容器宽度**: 最大 1400px，居中显示
- **背景**: 使用 `var(--bg-color)` 深色背景
- **内边距**: 2rem
- **响应式**: 适配不同屏幕宽度

### 1.2 页面头部 (Header)
| 元素 | 描述 |
|------|------|
| 返回按钮 | `← 返回` 导航到首页 |
| 标题 | "系统监控仪表盘" |
| 查看日志按钮 | `📋 查看日志` 打开 Log Modal |
| 刷新提示 | "每5秒自动刷新" |

---

## 2. Chrome 风格标签页

### 2.1 标签配置
| Tab ID | 标签名称 | 图标 | 日志类型 |
|--------|----------|------|----------|
| `download` | 文件下载 | 📥 | `download` |
| `training` | 训练流程 | 🧠 | `training` |
| `api` | API 应用 | 🚀 | `sync` |

### 2.2 标签样式 (Chrome Style)
```css
.tab-btn {
  border-radius: 0.75rem 0.75rem 0 0;  /* 圆角顶部 */
  min-width: 120px;
}

.tab-btn.active {
  background: var(--accent-cyan);      /* 青色高亮 */
  color: #000;
}

/* 底部曲线效果 - 伪元素实现 */
.tab-btn.active::before { box-shadow: 6px 0 0 0 var(--accent-cyan); }
.tab-btn.active::after  { box-shadow: -6px 0 0 0 var(--accent-cyan); }
```

---

## 3. 标签页内容

### 3.1 文件下载标签 (`download`)

**进度概览卡片 (3列)**:
| 指标 | 图标 | 数据源 |
|------|------|--------|
| 已完成天数 | 📅 | `download.completedDays / download.totalDays` |
| 总文件数 | 📁 | `download.filesDownloaded` |
| 当前日期 | ⏳ | `download.currentDate` |

**总体进度条**:
- 百分比 = `completedDays / totalDays * 100`
- 渐变色: `var(--accent-blue)` → `var(--accent-cyan)`

**每日下载详情表格**:
| 列 | 数据源 |
|----|--------|
| 状态 | ✅ (completed) / ⏳ (running) / ○ (pending) |
| 日期 | `dateProgress[].date` |
| 卫星数据 | `satelliteFiles / satelliteTotal` |
| NEA 数据 | `neaFiles / neaTotal` |

### 3.2 训练流程标签 (`training`)

**四阶段步进器**:
```
下载数据 → 预处理 → 训练 → 同步模型
```
- 状态: `pending` (灰) / `running` (紫) / `completed` (绿)
- 数据源: `training.phases[]`

**状态卡片 (3列)**:
| 指标 | 图标 | 数据源 |
|------|------|--------|
| 当前处理日期 | 📅 | `training.currentDate` |
| 已完成批次 | 📊 | `training.completedBatches` |
| 总 Epochs | 🔄 | `training.totalEpochs` |

**训练历史表格**:
| 列 | 数据源 |
|----|--------|
| 状态 | ✅ / ❌ (`success` 字段) |
| 日期 | `timestamp` |
| 数据范围 | `dateRange` |
| 时长 | `duration` |
| MAE | `mae` (蓝色) |
| RMSE | `rmse` (青色) |

### 3.3 API 应用标签 (`api`)

**同步状态卡片 (2列)**:
| 指标 | 图标 | 数据源 |
|------|------|--------|
| 模型同步 | ✅/⏳ | `sync.modelSynced` |
| 传感器数据 | ✅/⏳ | `sync.sensorDataSynced` |

**同步详情**:
- 最后同步时间: `sync.lastSyncTime`
- 服务状态: `sync.status` (🟢 正常 / 🟡 异常)

---

## 4. 日志查看功能 (Log Modal)

### 4.1 触发方式
- 点击 Header 中的 `📋 查看日志` 按钮
- 自动根据当前激活的标签页加载对应日志

### 4.2 日志来源映射
| 标签页 | Log Type | 来源 | 路径 |
|--------|----------|------|------|
| 文件下载 | `download` | S3 | `logs/download.log` |
| 训练流程 | `training` | S3 | `logs/training.log` |
| API 应用 | `sync` | 本地 | `/var/log/model_sync.log` |

### 4.3 Modal UI 规格
- **背景**: 全屏半透明覆盖 `rgba(15, 23, 42, 0.9)` + 模糊
- **内容区**: 最大 1000px 宽，最大 80vh 高
- **关闭方式**: 点击 × 按钮 或 点击 Modal 外部背景

### 4.4 日志内容样式
- 字体: `monospace`, 0.8rem
- 行高: 1.6
- **高亮规则**:
  | 关键词 | 颜色 |
  |--------|------|
  | `ERROR` | `var(--accent-red)` 红色 |
  | `WARNING` | `var(--accent-orange)` 橙色 |
  | `SUCCESS` / `✓` | `var(--accent-green)` 绿色 |
  | 其他 | `var(--text-secondary)` 灰色 |

---

## 5. API 端点

### 5.1 监控数据 API
- **端点**: `GET /monitor/overview`
- **刷新频率**: 每 5 秒
- **响应结构**:
```typescript
interface OverviewStatus {
  currentStage: 'download' | 'training' | 'sync' | 'idle';
  download: DownloadStatus;
  training: TrainingStatus;
  sync: SyncStatus;
}
```

### 5.2 日志 API
- **端点**: `GET /monitor/logs/{log_type}?lines=200`
- **参数**: `log_type` = `download` | `training` | `sync`
- **响应结构**:
```typescript
interface LogResponse {
  type: string;
  source: 's3' | 'local';
  path: string;
  lines: string[];
  timestamp: string;
}
```

---

## 6. 技术实现

### 6.1 前端组件
- **文件**: `frontend/src/pages/TrainingMonitor.tsx`
- **框架**: React + TypeScript
- **样式**: CSS classes in `frontend/src/index.css`

### 6.2 CSS 类名
| 类名 | 用途 |
|------|------|
| `.tab-nav` | 标签导航容器 |
| `.tab-btn` | 标签按钮 |
| `.tab-btn.active` | 激活状态标签 |
| `.tab-content` | 标签内容区 |
| `.metric-card` | 指标卡片 |
| `.log-panel` | 日志 Modal 背景 |

---

## 7. 版本历史

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-01-29 | v1.0 | 实现三标签页架构、Chrome 风格标签、日志查看功能 |
