import { useState, useEffect, useCallback } from 'react';
import './index.css';
import type { OverviewStatus } from './types';
import { getOverview, getLogs } from './api';

// 图标
const Icons = {
  download: '📥',
  training: '🧠',
  api: '☁️',
  check: '✅',
  error: '❌',
  loading: '⏳',
  running: '🔄',
  pending: '⏸️',
  log: '📋',
  close: '✕'
};

// 标签页类型
type TabType = 'download' | 'training' | 'api';

// 标签页导航
function TabNav({ activeTab, onTabChange }: {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
}) {
  const tabs = [
    { id: 'download' as TabType, label: 'File Download', icon: Icons.download },
    { id: 'training' as TabType, label: 'Training Process', icon: Icons.training },
    { id: 'api' as TabType, label: 'API Application', icon: Icons.api }
  ];

  return (
    <div className="tab-nav">
      {tabs.map(tab => (
        <button
          key={tab.id}
          className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
          onClick={() => onTabChange(tab.id)}
        >
          <span className="tab-icon">{tab.icon}</span>
          <span className="tab-label">{tab.label}</span>
        </button>
      ))}
    </div>
  );
}

// Tab 1: File Download
function DownloadTab({
  data,
  onViewLogs
}: {
  data: OverviewStatus['download'];
  onViewLogs: () => void;
}) {
  const progress = Math.round((data.completedDays / data.totalDays) * 100);

  // 使用 API 返回的真实数据
  const dateProgress = data.dateProgress || [];

  return (
    <div className="tab-content">
      <div className="tab-header">
        <h2>{Icons.download} 文件下载进度</h2>
        <span className={`status-badge ${data.status}`}>
          {data.status === 'running' ? '运行中' : data.status}
        </span>
      </div>

      {/* 总体进度 */}
      <div className="progress-overview">
        <div className="progress-bar-container">
          <div className="progress-bar" style={{ width: `${progress}%` }} />
        </div>
        <div className="progress-stats">
          <div className="stat">
            <span className="stat-label">总体进度</span>
            <span className="stat-value">{data.completedDays} / {data.totalDays} 天 ({progress}%)</span>
          </div>
          <div className="stat">
            <span className="stat-label">已下载文件</span>
            <span className="stat-value">{data.filesDownloaded.toLocaleString()}</span>
          </div>
          <div className="stat">
            <span className="stat-label">并行进程</span>
            <span className="stat-value">{data.parallelProcesses}</span>
          </div>
        </div>
      </div>

      {/* 按日期详情表格 */}
      <div className="data-table-container">
        <h3>按日期下载状态</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>日期</th>
              <th>卫星文件</th>
              <th>NEA 数据</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {dateProgress.map(row => (
              <tr key={row.date} className={row.status}>
                <td>{row.date}</td>
                <td>{row.satelliteFiles} / {row.satelliteTotal}</td>
                <td>{row.neaFiles} / {row.neaTotal}</td>
                <td>
                  {row.status === 'completed' && <span className="status-icon success">{Icons.check}</span>}
                  {row.status === 'running' && <span className="status-icon running">{Icons.running}</span>}
                  {row.status === 'pending' && <span className="status-icon pending">{Icons.pending}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button className="view-logs-btn" onClick={onViewLogs}>
        {Icons.log} 查看日志
      </button>
    </div>
  );
}

// Tab 2: Training Process
function TrainingTab({
  data,
  onViewLogs
}: {
  data: OverviewStatus['training'];
  onViewLogs: () => void;
}) {
  const phases = [
    { name: '从 S3 下载数据', status: data.phases[0]?.status || 'pending', progress: data.phases[0]?.progress },
    { name: '预处理 (裁剪新加坡)', status: data.phases[1]?.status || 'pending', progress: data.phases[1]?.progress },
    { name: '批量训练', status: data.phases[2]?.status || 'pending', progress: data.phases[2]?.progress },
    { name: '上传模型到 S3', status: data.phases[3]?.status || 'pending', progress: data.phases[3]?.progress }
  ];

  return (
    <div className="tab-content">
      <div className="tab-header">
        <h2>{Icons.training} 训练流程</h2>
        <span className={`status-badge ${data.status}`}>
          {data.status === 'running' ? '运行中' : data.status === 'waiting' ? '等待数据' : data.status}
        </span>
      </div>

      {/* 当前批次信息 */}
      <div className="batch-info">
        <div className="info-card">
          <span className="info-label">当前处理日期</span>
          <span className="info-value">{data.currentDate || '-'}</span>
        </div>
        <div className="info-card">
          <span className="info-label">已完成批次</span>
          <span className="info-value">{data.completedBatches}</span>
        </div>
        <div className="info-card">
          <span className="info-label">总 Epochs</span>
          <span className="info-value">{data.totalEpochs}</span>
        </div>
        {data.diskUsage && (
          <div className="info-card">
            <span className="info-label">磁盘使用</span>
            <span className="info-value">{data.diskUsage}</span>
          </div>
        )}
      </div>

      {/* 训练历史 - 移到顶部 */}
      <div className="data-table-container">
        <h3>训练历史</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>数据范围</th>
              <th>MAE (mm)</th>
              <th>RMSE (mm)</th>
              <th>Epochs</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {data.history && data.history.length > 0 ? (
              data.history.slice().reverse().map((item) => (
                <tr key={item.id} className={item.success ? 'completed' : 'error'}>
                  <td>{item.dateRange}</td>
                  <td>{item.mae.toFixed(4)}</td>
                  <td>{item.rmse.toFixed(4)}</td>
                  <td>{item.epochs}</td>
                  <td>
                    {item.success ? (
                      <span className="status-icon success">{Icons.check}</span>
                    ) : (
                      <span className="status-icon error">{Icons.error}</span>
                    )}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="empty-row">暂无训练记录</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* 阶段进度 */}
      <div className="phases-container">
        <h3>流程阶段</h3>
        <div className="phases-list">
          {phases.map((phase, i) => (
            <div key={i} className={`phase-item ${phase.status}`}>
              <div className="phase-number">{i + 1}</div>
              <div className="phase-details">
                <span className="phase-name">{phase.name}</span>
                <div className="phase-progress-bar">
                  <div
                    className="phase-progress-fill"
                    style={{ width: `${phase.progress || 0}%` }}
                  />
                </div>
              </div>
              <div className="phase-status">
                {phase.status === 'completed' && Icons.check}
                {phase.status === 'running' && `${phase.progress || 0}%`}
                {phase.status === 'pending' && '待处理'}
              </div>
            </div>
          ))}
        </div>
      </div>

      <button className="view-logs-btn" onClick={onViewLogs}>
        {Icons.log} 查看日志
      </button>
    </div>
  );
}

// Tab 3: API Application
function ApiTab({
  data,
  onViewLogs
}: {
  data: OverviewStatus['sync'];
  onViewLogs: () => void;
}) {
  const healthChecks = [
    { endpoint: '/predict', status: 'ok' },
    { endpoint: '/health', status: 'ok' },
    { endpoint: '/training-status', status: 'ok' }
  ];

  return (
    <div className="tab-content">
      <div className="tab-header">
        <h2>{Icons.api} API Application</h2>
        <span className={`status-badge ${data.status}`}>
          {data.status === 'ok' ? '正常' : data.status}
        </span>
      </div>

      {/* 数据就绪状态 */}
      <div className="readiness-container">
        <h3>数据就绪状态</h3>
        <div className="readiness-list">
          <div className={`readiness-item ${data.modelSynced ? 'ready' : 'pending'}`}>
            <span className="readiness-icon">{data.modelSynced ? Icons.check : Icons.loading}</span>
            <div className="readiness-details">
              <span className="readiness-name">模型文件</span>
              <span className="readiness-status">
                {data.modelSynced ? '已同步' : '同步中'}
              </span>
            </div>
          </div>
          <div className={`readiness-item ${data.sensorDataSynced ? 'ready' : 'pending'}`}>
            <span className="readiness-icon">{data.sensorDataSynced ? Icons.check : Icons.loading}</span>
            <div className="readiness-details">
              <span className="readiness-name">传感器数据</span>
              <span className="readiness-status">
                {data.sensorDataSynced ? '已同步' : '同步中'}
              </span>
            </div>
          </div>
          <div className="readiness-item ready">
            <span className="readiness-icon">{Icons.check}</span>
            <div className="readiness-details">
              <span className="readiness-name">预测服务</span>
              <span className="readiness-status">可用</span>
            </div>
          </div>
        </div>
        <div className="last-sync">
          最后同步时间: {data.lastSyncTime}
        </div>
      </div>

      {/* API 健康检查 */}
      <div className="health-container">
        <h3>API 健康检查</h3>
        <div className="health-list">
          {healthChecks.map(check => (
            <div key={check.endpoint} className={`health-item ${check.status}`}>
              <span className="health-endpoint">{check.endpoint}</span>
              <span className="health-status">
                {check.status === 'ok' ? `${Icons.check} 200 OK` : `${Icons.error} Error`}
              </span>
            </div>
          ))}
        </div>
      </div>

      <button className="view-logs-btn" onClick={onViewLogs}>
        {Icons.log} 查看日志
      </button>
    </div>
  );
}

// 日志模态框
function LogModal({
  title,
  logs,
  onClose
}: {
  title: string;
  logs: string[];
  onClose: () => void;
}) {
  const getLineClass = (line: string) => {
    if (line.includes('ERROR') || line.includes('❌')) return 'error';
    if (line.includes('SUCCESS') || line.includes('✅')) return 'success';
    if (line.includes('WARNING') || line.includes('⚠️')) return 'warning';
    if (line.includes('INFO')) return 'info';
    return '';
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div className="log-modal" onClick={handleBackdropClick}>
      <div className="log-modal-inner">
        <h3>
          {Icons.log} {title}
          <button className="close-btn" onClick={onClose}>{Icons.close}</button>
        </h3>
        <div className="log-content">
          {logs.map((line, i) => (
            <div key={i} className={`log-line ${getLineClass(line)}`}>{line}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

// 主应用
function App() {
  const [data, setData] = useState<OverviewStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('download');
  const [activeLog, setActiveLog] = useState<string | null>(null);
  const [logContent, setLogContent] = useState<string[]>([]);

  const fetchData = useCallback(async () => {
    try {
      const overview = await getOverview();
      setData(overview);
      setLastUpdate(new Date());
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleViewLogs = async (type: string) => {
    setActiveLog(type);
    setLogContent(['加载中...']);
    try {
      const response = await getLogs(type, 100);
      if (response.lines && response.lines.length > 0) {
        setLogContent(response.lines);
      } else if (response.message) {
        setLogContent([response.message]);
      } else {
        setLogContent(['暂无日志内容']);
      }
    } catch (error) {
      console.error('Failed to fetch logs:', error);
      setLogContent(['获取日志失败: ' + String(error)]);
    }
  };

  if (loading) {
    return (
      <div className="dashboard">
        <div className="loading">
          <div className="spinner" />
          加载中...
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="dashboard">
        <div className="loading">无法加载数据</div>
      </div>
    );
  }

  return (
    <div className="dashboard">
      <header className="header">
        <h1>🌤️ Weather AI 训练监控</h1>
        <span className="last-update">
          最后更新: {lastUpdate?.toLocaleTimeString('zh-CN')}
        </span>
      </header>

      <TabNav activeTab={activeTab} onTabChange={setActiveTab} />

      <div className="tab-panel">
        {activeTab === 'download' && (
          <DownloadTab data={data.download} onViewLogs={() => handleViewLogs('download')} />
        )}
        {activeTab === 'training' && (
          <TrainingTab data={data.training} onViewLogs={() => handleViewLogs('training')} />
        )}
        {activeTab === 'api' && (
          <ApiTab data={data.sync} onViewLogs={() => handleViewLogs('sync')} />
        )}
      </div>

      {activeLog && (
        <LogModal
          title={`${activeLog} 日志`}
          logs={logContent}
          onClose={() => setActiveLog(null)}
        />
      )}
    </div>
  );
}

export default App;
