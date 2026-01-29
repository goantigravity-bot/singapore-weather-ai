# Configuration Page 文档

## 概述

配置页面允许用户自定义天气预报面板和地图的显示选项。所有配置使用 localStorage 持久化存储。

**访问地址**：`/settings`

---

## 功能

### 1. 天气指标显示

控制预报面板中显示哪些天气数据：

| 指标 | 图标 | 说明 |
|-----|------|------|
| Rainfall Prediction | 🌧️ | 降雨量预测 |
| Temperature | 🌡️ | 温度 |
| Humidity | 💧 | 湿度 |
| PM2.5 (Air Quality) | 😷 | 空气质量 |

### 2. 地图显示选项

| 选项 | 图标 | 说明 |
|-----|------|------|
| Interpolation Triangle | 📐 | 显示插值三角形 |
| Weather Station Markers | 📍 | 显示气象站标记点 |

---

## 技术实现

### 架构

```
ConfigContext (React Context)
    ↓
localStorage (持久化)
    ↓
Components (消费配置)
```

### 相关文件

| 文件 | 说明 |
|-----|------|
| [SettingsPage.tsx](file:///Users/jinhui/development/tools/claude-skill/frontend/src/pages/SettingsPage.tsx) | 配置页面 UI |
| [ConfigContext.tsx](file:///Users/jinhui/development/tools/claude-skill/frontend/src/context/ConfigContext.tsx) | 配置状态管理 |
| [App.tsx](file:///Users/jinhui/development/tools/claude-skill/frontend/src/App.tsx#L47) | 路由配置 |

### ConfigContext API

```typescript
interface ConfigState {
    metrics: Set<'rain' | 'temp' | 'hum' | 'pm25'>;
    toggleMetric: (m: Metric) => void;
    showTriangle: boolean;
    toggleShowTriangle: () => void;
    showStations: boolean;
    toggleShowStations: () => void;
}
```

### localStorage Keys

| Key | 类型 | 默认值 |
|-----|------|--------|
| `forecast_metrics` | `string[]` | `['rain', 'temp', 'hum', 'pm25']` |
| `show_triangle` | `boolean` | `false` |
| `show_stations` | `boolean` | `true` |

---

## 路由说明

配置页面属于**独立页面**，不加载地图组件：

```typescript
// App.tsx
const isStandalonePage = ['/training', '/settings', '/stats', '/about'].includes(location.pathname);
```

这确保设置页面能快速加载，无需等待地图或地理位置初始化。

---

## 截图

![Configuration Page](/Users/jinhui/.gemini/antigravity/brain/5ca845c8-93a0-405a-a524-1366b017b59d/.system_generated/click_feedback/click_feedback_1769696614412.png)
