import { useState, useEffect, useCallback } from 'react';
import './index.css';
import type { OverviewStatus } from './types';
import { getOverview, getLogs } from './api';

// 图标组件
const Icons = {
  download: '📥',
  training: '🧠',
  sync: '☁️',
  check: '✅',
  error: '❌',
  loading: '⏳',
  log: '📋',
  close: '✕'
};

// 进度环组件
function ProgressRing({ progress, size = 80 }: { progress: number; size?: number }) {
  const strokeWidth = 8;
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (progress / 100) * circumference;

  return (
    <div className="progress-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle className="bg" cx={size / 2} cy={size / 2} r={radius} />
        <circle
          className="progress"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <span className="progress-text">{progress}%</span>
    </div>
  );
}

// 端到端管道进度组件
function PipelineProgress({ currentStage }: { currentStage: string }) {
  const stages = [
    { id: 'download', label: 'FTP下载', icon: '📥' },
    { id: 'storage', label: 'S3存储', icon: '🗄️' },
    { id: 'training-download', label: '训练下载', icon: '⬇️' },
    { id: 'preprocess', label: '预处理', icon: '⚙️' },
    { id: 'training', label: '训练', icon: '🧠' },
    { id: 'sync', label: 'API同步', icon: '☁️' }
  ];

  // 根据当前阶段计算进度
  const getStageStatus = (stageId: string) => {
    const stageOrder = ['download', 'storage', 'training-download', 'preprocess', 'training', 'sync'];
    const currentIndex = stageOrder.indexOf(currentStage);
    const stageIndex = stageOrder.indexOf(stageId);

    if (stageIndex < currentIndex) return 'completed';
    if (stageIndex === currentIndex) return 'running';
    return 'pending';
  };

  const completedStages = stages.filter(s => getStageStatus(s.id) === 'completed').length;
  const progressPercent = (completedStages / stages.length) * 100;

  return (
    <div className="pipeline-progress">
      <h2>端到端流程进度</h2>
      <div className="pipeline-steps">
        <div className="pipeline-line">
          <div className="pipeline-line-progress" style={{ width: `${progressPercent}%` }} />
        </div>
        {stages.map((stage) => (
          <div key={stage.id} className="pipeline-step">
            <div className={`step-icon ${getStageStatus(stage.id)}`}>
              {stage.icon}
            </div>
            <span className="step-label">{stage.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// 下载状态卡片
function DownloadCard({
  data,
  onViewLogs
}: {
  data: OverviewStatus['download'];
  onViewLogs: () => void;
}) {
  const progress = Math.round((data.completedDays / data.totalDays) * 100);

  return (
    <div className="status-card">
      <div className="card-header">
        <h3 className="card-title">{Icons.download} FTP → S3 下载</h3>
        <span className={`card-status ${data.status}`}>
          {data.status === 'running' ? '运行中' : data.status === 'completed' ? '已完成' : data.status}
        </span>
      </div>

      <div className="progress-ring-container">
        <ProgressRing progress={progress} />
        <div className="progress-details">
          <div className="progress-stat">
            <span className="stat-label">已完成天数</span>
            <span className="stat-value">{data.completedDays} / {data.totalDays}</span>
          </div>
          <div className="progress-stat">
            <span className="stat-label">已下载文件</span>
            <span className="stat-value">{data.filesDownloaded.toLocaleString()}</span>
          </div>
          <div className="progress-stat">
            <span className="stat-label">并行进程</span>
            <span className="stat-value">{data.parallelProcesses}</span>
          </div>
        </div>
      </div>

      <button className="view-logs-btn" onClick={onViewLogs}>
        {Icons.log} 查看日志
      </button>
    </div>
  );
}

// 训练状态卡片
function TrainingCard({
  data,
  onViewLogs
}: {
  data: OverviewStatus['training'];
  onViewLogs: () => void;
}) {
  return (
    <div className="status-card">
      <div className="card-header">
        <h3 className="card-title">{Icons.training} 训练流程</h3>
        <span className={`card-status ${data.status}`}>
          {data.status === 'running' ? '运行中' : data.status === 'waiting' ? '等待数据' : data.status}
        </span>
      </div>

      <div className="progress-details" style={{ marginBottom: '1rem' }}>
        <div className="progress-stat">
          <span className="stat-label">当前处理日期</span>
          <span className="stat-value">{data.currentDate || '-'}</span>
        </div>
        <div className="progress-stat">
          <span className="stat-label">已完成批次</span>
          <span className="stat-value">{data.completedBatches}</span>
        </div>
        <div className="progress-stat">
          <span className="stat-label">总 Epochs</span>
          <span className="stat-value">{data.totalEpochs}</span>
        </div>
        {data.diskUsage && (
          <div className="progress-stat">
            <span className="stat-label">磁盘使用</span>
            <span className="stat-value">{data.diskUsage}</span>
          </div>
        )}
      </div>

      <div className="phases">
        {data.phases.map((phase, i) => (
          <div key={i} className="phase">
            <div className={`phase-indicator ${phase.status}`} />
            <span className="phase-name">{phase.name}</span>
            {phase.progress !== undefined && (
              <span className="phase-status">{phase.progress}%</span>
            )}
          </div>
        ))}
      </div>

      <button className="view-logs-btn" onClick={onViewLogs}>
        {Icons.log} 查看日志
      </button>
    </div>
  );
}

// 同步状态卡片
function SyncCard({
  data,
  onViewLogs
}: {
  data: OverviewStatus['sync'];
  onViewLogs: () => void;
}) {
  return (
    <div className="status-card">
      <div className="card-header">
        <h3 className="card-title">{Icons.sync} API 同步</h3>
        <span className={`card-status ${data.status === 'ok' ? 'completed' : data.status}`}>
          {data.status === 'ok' ? '正常' : data.status}
        </span>
      </div>

      <div className="progress-details">
        <div className="progress-stat">
          <span className="stat-label">模型同步</span>
          <span className="stat-value">
            {data.modelSynced ? Icons.check : Icons.loading}
          </span>
        </div>
        <div className="progress-stat">
          <span className="stat-label">传感器数据</span>
          <span className="stat-value">
            {data.sensorDataSynced ? Icons.check : Icons.loading}
          </span>
        </div>
        <div className="progress-stat">
          <span className="stat-label">最后同步时间</span>
          <span className="stat-value">{data.lastSyncTime || '-'}</span>
        </div>
      </div>

      <button className="view-logs-btn" onClick={onViewLogs}>
        {Icons.log} 查看日志
      </button>
    </div>
  );
}

// 日志面板
function LogPanel({
  title,
  logs,
  onClose
}: {
  title: string;
  logs: string[];
  onClose: () => void;
}) {
  // 根据日志内容高亮
  const getLineClass = (line: string) => {
    if (line.includes('ERROR') || line.includes('❌')) return 'error';
    if (line.includes('SUCCESS') || line.includes('✅')) return 'success';
    if (line.includes('WARNING') || line.includes('⚠️')) return 'warning';
    if (line.includes('INFO')) return 'info';
    return '';
  };

  return (
    <div className="log-panel">
      <h3>
        {Icons.log} {title}
        <button className="close-btn" onClick={onClose}>{Icons.close}</button>
      </h3>
      <div className="log-content">
        {logs.map((line, i) => (
          <div key={i} className={`log-line ${getLineClass(line)}`}>
            {line}
          </div>
        ))}
      </div>
    </div>
  );
}

// 主应用
function App() {
  const [data, setData] = useState<OverviewStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [activeLog, setActiveLog] = useState<string | null>(null);
  const [logContent, setLogContent] = useState<string[]>([]);

  // 获取数据
  const fetchData = useCallback(async () => {
    try {
      // 使用真实 API 数据
      const overview = await getOverview();
      setData(overview);
      setLastUpdate(new Date());
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  // 初始加载 + 10秒自动刷新
  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // 查看日志 - 调用真实 API
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

      <PipelineProgress currentStage={data.currentStage} />

      <div className="status-grid">
        <DownloadCard
          data={data.download}
          onViewLogs={() => handleViewLogs('download')}
        />
        <TrainingCard
          data={data.training}
          onViewLogs={() => handleViewLogs('training')}
        />
        <SyncCard
          data={data.sync}
          onViewLogs={() => handleViewLogs('sync')}
        />
      </div>

      {activeLog && (
        <LogPanel
          title={`${activeLog} 日志`}
          logs={logContent}
          onClose={() => setActiveLog(null)}
        />
      )}
    </div>
  );
}

export default App;
