import React, { useEffect, useState } from 'react';
import { API_BASE_URL } from '../config';
import { useNavigate } from 'react-router-dom';
import { LABELS } from '../i18n/labels';

// Types based on /monitor/overview API
interface DateProgress {
    date: string;
    satelliteFiles: number;
    satelliteTotal: number;
    neaFiles: number;
    neaTotal: number;
    status: 'pending' | 'running' | 'completed';
}

interface DownloadStatus {
    currentDate: string | null;
    completedDays: number;
    totalDays: number;
    filesDownloaded: number;
    status: string;
    lastUpdate: string;
    dateProgress: DateProgress[];
}

interface TrainingPhase {
    name: string;
    status: 'pending' | 'running' | 'completed' | 'error';
}

interface TrainingHistoryItem {
    id: number;
    timestamp: string;
    dateRange: string;
    epochs: number;
    duration: string;
    mae: number;
    rmse: number;
    success: boolean;
}

interface TrainingStatus {
    currentDate: string | null;
    completedBatches: number;
    totalEpochs: number;
    currentPhase: string;
    phases: TrainingPhase[];
    status: string;
    lastUpdate: string;
    history: TrainingHistoryItem[];
}

interface SyncStatus {
    modelSynced: boolean;
    sensorDataSynced: boolean;
    lastSyncTime: string | null;
    status: string;
}

interface OverviewStatus {
    currentStage: 'download' | 'training' | 'sync' | 'idle' | 'unknown';
    download: DownloadStatus;
    training: TrainingStatus;
    sync: SyncStatus;
}

// Tab 配置
type TabType = 'download' | 'training' | 'api';

const TABS: { id: TabType; label: string; icon: string }[] = [
    { id: 'download', label: LABELS.monitor.tabs.download.label, icon: '📥' },
    { id: 'training', label: LABELS.monitor.tabs.training.label, icon: '🧠' },
    { id: 'api', label: LABELS.monitor.tabs.api.label, icon: '🚀' }
];

// Log 响应接口
interface LogResponse {
    type: string;
    source?: string;
    path?: string;
    message?: string;
    lines: string[];
    timestamp: string;
}

// 日志类型映射
const LOG_TYPE_MAP: Record<TabType, string> = {
    download: 'download',
    training: 'training',
    api: 'sync'
};

const TrainingMonitor: React.FC = () => {
    const [overview, setOverview] = useState<OverviewStatus | null>(null);
    const [activeTab, setActiveTab] = useState<TabType>('download');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const navigate = useNavigate();

    // 日志相关状态
    const [showLogModal, setShowLogModal] = useState(false);
    const [logs, setLogs] = useState<LogResponse | null>(null);
    const [logLoading, setLogLoading] = useState(false);

    const fetchData = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/monitor/overview`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            setOverview(data);
            setError(null);
        } catch (err) {
            console.error("Failed to fetch monitor data", err);
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            setLoading(false);
        }
    };

    // 获取日志内容
    const fetchLogs = async (logType: string) => {
        setLogLoading(true);
        try {
            const response = await fetch(`${API_BASE_URL}/monitor/logs/${logType}?lines=200`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            setLogs(data);
            setShowLogModal(true);
        } catch (err) {
            console.error("Failed to fetch logs", err);
            setLogs({ type: logType, lines: [`Error loading logs: ${err}`], timestamp: new Date().toISOString() });
            setShowLogModal(true);
        } finally {
            setLogLoading(false);
        }
    };

    // 打开当前标签页的日志
    const handleViewLogs = () => {
        const logType = LOG_TYPE_MAP[activeTab];
        fetchLogs(logType);
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 5000);
        return () => clearInterval(interval);
    }, []);

    if (loading && !overview) {
        return (
            <div className="dashboard-overlay" style={{ zIndex: 2000 }}>
                <div style={{ textAlign: 'center', padding: '2rem' }}>
                    <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>⏳</div>
                    {LABELS.common.loading}
                </div>
            </div>
        );
    }

    if (error && !overview) {
        return (
            <div className="dashboard-overlay" style={{ zIndex: 2000 }}>
                <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--accent-red)' }}>
                    <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>❌</div>
                    {LABELS.common.error}: {error}
                </div>
            </div>
        );
    }

    const { download, training, sync } = overview!;

    // 下载标签页内容
    const renderDownloadTab = () => {
        const downloadPct = Math.round((download.completedDays / download.totalDays) * 100);

        return (
            <div>
                {/* 进度概览 */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                    <div className="metric-card">
                        <div className="metric-icon">📅</div>
                        <div className="metric-info">
                            <div className="metric-label">{LABELS.monitor.tabs.download.completedDays}</div>
                            <div className="metric-value">{download.completedDays}/{download.totalDays}</div>
                        </div>
                    </div>
                    <div className="metric-card">
                        <div className="metric-icon">📁</div>
                        <div className="metric-info">
                            <div className="metric-label">{LABELS.monitor.tabs.download.totalFiles}</div>
                            <div className="metric-value">{download.filesDownloaded.toLocaleString()}</div>
                        </div>
                    </div>
                    <div className="metric-card">
                        <div className="metric-icon">⏳</div>
                        <div className="metric-info">
                            <div className="metric-label">{LABELS.monitor.tabs.download.currentDate}</div>
                            <div className="metric-value" style={{ fontSize: '1.2rem' }}>
                                {download.currentDate || 'Idle'}
                            </div>
                        </div>
                    </div>
                </div>

                {/* 总进度条 */}
                <div style={{ marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                        <span style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>{LABELS.monitor.tabs.download.overallProgress}</span>
                        <span style={{ color: 'var(--accent-cyan)', fontWeight: 'bold' }}>{downloadPct}%</span>
                    </div>
                    <div style={{ height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
                        <div style={{
                            width: `${downloadPct}%`,
                            height: '100%',
                            background: 'linear-gradient(90deg, var(--accent-blue), var(--accent-cyan))',
                            transition: 'width 0.3s'
                        }} />
                    </div>
                </div>

                {/* 每日详情表格 */}
                <h4 style={{ margin: '0 0 1rem 0', color: 'var(--text-primary)' }}>{LABELS.monitor.tabs.download.dailyDetails}</h4>
                <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                    <table style={{ width: '100%', fontSize: '0.8rem', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', position: 'sticky', top: 0, background: 'var(--bg-card)' }}>
                                <th style={{ padding: '0.5rem', textAlign: 'left', color: 'var(--text-secondary)' }}>{LABELS.monitor.tabs.download.table.status}</th>
                                <th style={{ padding: '0.5rem', textAlign: 'left', color: 'var(--text-secondary)' }}>{LABELS.monitor.tabs.download.table.date}</th>
                                <th style={{ padding: '0.5rem', textAlign: 'left', color: 'var(--text-secondary)' }}>{LABELS.monitor.tabs.download.table.satelliteData}</th>
                                <th style={{ padding: '0.5rem', textAlign: 'left', color: 'var(--text-secondary)' }}>{LABELS.monitor.tabs.download.table.neaData}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {download.dateProgress.map((dp: DateProgress) => (
                                <tr key={dp.date} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                    <td style={{ padding: '0.5rem' }}>
                                        {dp.status === 'completed' ? '✅' : dp.status === 'running' ? '⏳' : '○'}
                                    </td>
                                    <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>{dp.date}</td>
                                    <td style={{ padding: '0.5rem' }}>
                                        <span style={{ color: dp.satelliteFiles >= dp.satelliteTotal ? 'var(--accent-green)' : 'var(--text-secondary)' }}>
                                            {dp.satelliteFiles}/{dp.satelliteTotal}
                                        </span>
                                    </td>
                                    <td style={{ padding: '0.5rem' }}>
                                        <span style={{ color: dp.neaFiles >= dp.neaTotal ? 'var(--accent-green)' : 'var(--text-secondary)' }}>
                                            {dp.neaFiles}/{dp.neaTotal}
                                        </span>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    };

    // 训练标签页内容
    const renderTrainingTab = () => (
        <div>
            {/* 四阶段进度 */}
            <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                marginBottom: '1.5rem', padding: '1rem', background: 'rgba(255,255,255,0.03)', borderRadius: '12px'
            }}>
                {training.phases.map((phase: TrainingPhase, idx: number) => (
                    <React.Fragment key={phase.name}>
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
                            <div style={{
                                width: '36px', height: '36px', borderRadius: '50%',
                                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.875rem',
                                background: phase.status === 'completed' ? 'var(--accent-green)' :
                                    phase.status === 'running' ? 'var(--accent-purple)' : 'rgba(255,255,255,0.1)',
                                color: phase.status === 'pending' ? 'var(--text-secondary)' : 'white'
                            }}>
                                {phase.status === 'completed' ? '✓' : phase.status === 'running' ? '⏳' : idx + 1}
                            </div>
                            <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{phase.name}</span>
                        </div>
                        {idx < training.phases.length - 1 && (
                            <div style={{
                                flex: 1, height: '2px', margin: '0 0.5rem', marginBottom: '1.5rem',
                                background: phase.status === 'completed' ? 'var(--accent-green)' : 'rgba(255,255,255,0.1)'
                            }} />
                        )}
                    </React.Fragment>
                ))}
            </div>

            {/* 状态卡片 */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                <div className="metric-card">
                    <div className="metric-icon">📅</div>
                    <div className="metric-info">
                        <div className="metric-label">{LABELS.monitor.tabs.training.currentDate}</div>
                        <div className="metric-value" style={{ fontSize: '1.2rem' }}>{training.currentDate || 'Idle'}</div>
                    </div>
                </div>
                <div className="metric-card">
                    <div className="metric-icon">📊</div>
                    <div className="metric-info">
                        <div className="metric-label">{LABELS.monitor.tabs.training.completedBatches}</div>
                        <div className="metric-value">{training.completedBatches}</div>
                    </div>
                </div>
                <div className="metric-card">
                    <div className="metric-icon">🔄</div>
                    <div className="metric-info">
                        <div className="metric-label">{LABELS.monitor.tabs.training.totalEpochs}</div>
                        <div className="metric-value">{training.totalEpochs}</div>
                    </div>
                </div>
            </div>

            {/* 训练历史表格 */}
            <h4 style={{ margin: '0 0 1rem 0', color: 'var(--text-primary)' }}>{LABELS.monitor.tabs.training.history}</h4>
            <div style={{ maxHeight: '250px', overflowY: 'auto' }}>
                <table style={{ width: '100%', fontSize: '0.8rem', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', position: 'sticky', top: 0, background: 'var(--bg-card)' }}>
                            <th style={{ padding: '0.5rem', textAlign: 'left', color: 'var(--text-secondary)' }}>{LABELS.monitor.tabs.training.table.status}</th>
                            <th style={{ padding: '0.5rem', textAlign: 'left', color: 'var(--text-secondary)' }}>{LABELS.monitor.tabs.training.table.date}</th>
                            <th style={{ padding: '0.5rem', textAlign: 'left', color: 'var(--text-secondary)' }}>{LABELS.monitor.tabs.training.table.range}</th>
                            <th style={{ padding: '0.5rem', textAlign: 'left', color: 'var(--text-secondary)' }}>{LABELS.monitor.tabs.training.table.duration}</th>
                            <th style={{ padding: '0.5rem', textAlign: 'left', color: 'var(--text-secondary)' }}>{LABELS.monitor.tabs.training.table.mae}</th>
                            <th style={{ padding: '0.5rem', textAlign: 'left', color: 'var(--text-secondary)' }}>{LABELS.monitor.tabs.training.table.rmse}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {training.history.slice().reverse().map((run: TrainingHistoryItem) => (
                            <tr key={run.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                <td style={{ padding: '0.5rem' }}>{run.success ? '✅' : '❌'}</td>
                                <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>
                                    {new Date(run.timestamp).toLocaleDateString()}
                                </td>
                                <td style={{ padding: '0.5rem', color: 'var(--text-secondary)' }}>{run.dateRange}</td>
                                <td style={{ padding: '0.5rem' }}>{run.duration}</td>
                                <td style={{ padding: '0.5rem', fontFamily: 'monospace', color: 'var(--accent-blue)' }}>
                                    {run.mae.toFixed(4)}
                                </td>
                                <td style={{ padding: '0.5rem', fontFamily: 'monospace', color: 'var(--accent-cyan)' }}>
                                    {run.rmse.toFixed(4)}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );

    // API 标签页内容
    const renderApiTab = () => (
        <div>
            {/* 状态卡片 */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                <div className="metric-card" style={{ borderColor: sync.modelSynced ? 'var(--accent-green)' : 'transparent' }}>
                    <div className="metric-icon" style={{ fontSize: '2rem' }}>{sync.modelSynced ? '✅' : '⏳'}</div>
                    <div className="metric-info">
                        <div className="metric-label">{LABELS.monitor.tabs.api.modelSynced}</div>
                        <div className="metric-value" style={{ color: sync.modelSynced ? 'var(--accent-green)' : 'var(--accent-orange)' }}>
                            {sync.modelSynced ? LABELS.monitor.tabs.api.synced : LABELS.monitor.tabs.api.pending}
                        </div>
                    </div>
                </div>
                <div className="metric-card" style={{ borderColor: sync.sensorDataSynced ? 'var(--accent-green)' : 'transparent' }}>
                    <div className="metric-icon" style={{ fontSize: '2rem' }}>{sync.sensorDataSynced ? '✅' : '⏳'}</div>
                    <div className="metric-info">
                        <div className="metric-label">{LABELS.monitor.tabs.api.sensorData}</div>
                        <div className="metric-value" style={{ color: sync.sensorDataSynced ? 'var(--accent-green)' : 'var(--accent-orange)' }}>
                            {sync.sensorDataSynced ? LABELS.monitor.tabs.api.synced : LABELS.monitor.tabs.api.pending}
                        </div>
                    </div>
                </div>
            </div>

            {/* 同步详情 */}
            <div className="metric-card" style={{ marginBottom: '1rem' }}>
                <div className="metric-info" style={{ width: '100%' }}>
                    <div className="metric-label">{LABELS.monitor.tabs.api.lastSyncTime}</div>
                    <div className="metric-value" style={{ fontSize: '1.2rem' }}>{sync.lastSyncTime || 'Never'}</div>
                </div>
            </div>

            <div className="metric-card">
                <div className="metric-info" style={{ width: '100%' }}>
                    <div className="metric-label">{LABELS.monitor.tabs.api.serviceStatus}</div>
                    <div className="metric-value" style={{ fontSize: '1.2rem', color: sync.status === 'ok' ? 'var(--accent-green)' : 'var(--accent-orange)' }}>
                        {sync.status === 'ok' ? `🟢 ${LABELS.monitor.tabs.api.operational}` : `🟡 ${LABELS.monitor.tabs.api.statusPrefix}${sync.status}`}
                    </div>
                </div>
            </div>
        </div>
    );

    return (
        <div style={{
            width: '100%',
            minHeight: '100vh',
            background: 'var(--bg-color)',
            padding: '2rem',
            boxSizing: 'border-box',
            overflow: 'auto'
        }}>
            <div style={{ maxWidth: '1400px', margin: '0 auto' }}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
                    <button onClick={() => navigate('/')} className="quick-link-chip" style={{ padding: '8px 16px' }}>
                        ← {LABELS.common.backToHome}
                    </button>
                    <h2 style={{ margin: 0, color: 'var(--text-primary)', fontSize: '1.75rem' }}>{LABELS.monitor.title}</h2>
                    <button
                        onClick={handleViewLogs}
                        disabled={logLoading}
                        className="quick-link-chip"
                        style={{ marginLeft: 'auto', padding: '8px 16px' }}
                    >
                        {logLoading ? LABELS.common.loading : `📋 ${LABELS.monitor.viewLogs}`}
                    </button>
                    <span style={{ fontSize: '0.875rem', color: 'var(--text-secondary)' }}>
                        {LABELS.monitor.autoRefresh}
                    </span>
                </div>

                {/* Chrome-Style Tab Navigation */}
                <div className="tab-nav" style={{ marginBottom: 0 }}>
                    {TABS.map(tab => (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
                        >
                            <span style={{ fontSize: '1.25rem' }}>{tab.icon}</span>
                            <span>{tab.label}</span>
                        </button>
                    ))}
                </div>

                {/* Tab Content */}
                <div className="tab-content" style={{
                    background: 'var(--panel-bg)',
                    backdropFilter: 'blur(12px)',
                    borderRadius: '0 16px 16px 16px',
                    padding: '2rem',
                    border: '1px solid var(--panel-border)'
                }}>
                    {activeTab === 'download' && renderDownloadTab()}
                    {activeTab === 'training' && renderTrainingTab()}
                    {activeTab === 'api' && renderApiTab()}
                </div>

                {/* Last Update */}
                <div style={{ textAlign: 'right', fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '1rem' }}>
                    {LABELS.monitor.lastUpdate}: {new Date().toLocaleString()}
                </div>
            </div>

            {/* Log Modal */}
            {showLogModal && logs && (
                <div
                    className="log-panel"
                    onClick={(e) => { if (e.target === e.currentTarget) setShowLogModal(false); }}
                    style={{
                        position: 'fixed',
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        background: 'rgba(15, 23, 42, 0.9)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        zIndex: 3000,
                        padding: '2rem'
                    }}
                >
                    <div style={{
                        background: 'var(--panel-bg)',
                        backdropFilter: 'blur(12px)',
                        borderRadius: '16px',
                        padding: '1.5rem',
                        border: '1px solid var(--panel-border)',
                        width: '100%',
                        maxWidth: '1000px',
                        maxHeight: '80vh',
                        display: 'flex',
                        flexDirection: 'column'
                    }}>
                        {/* Modal Header */}
                        <div style={{ display: 'flex', alignItems: 'center', marginBottom: '1rem' }}>
                            <h3 style={{ margin: 0, color: 'var(--text-primary)' }}>
                                📋 {logs.type === 'download' ? LABELS.monitor.logs.title.download :
                                    logs.type === 'training' ? LABELS.monitor.logs.title.training :
                                        LABELS.monitor.logs.title.api}
                            </h3>
                            <span style={{ marginLeft: '1rem', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                                {logs.source} - {logs.path}
                            </span>
                            <button
                                onClick={() => setShowLogModal(false)}
                                style={{
                                    marginLeft: 'auto',
                                    background: 'transparent',
                                    border: 'none',
                                    color: 'var(--text-secondary)',
                                    fontSize: '1.5rem',
                                    cursor: 'pointer'
                                }}
                            >
                                ×
                            </button>
                        </div>

                        {/* Log Content */}
                        <div style={{
                            flex: 1,
                            overflowY: 'auto',
                            background: 'rgba(0, 0, 0, 0.3)',
                            borderRadius: '8px',
                            padding: '1rem',
                            fontFamily: 'monospace',
                            fontSize: '0.8rem',
                            lineHeight: '1.6',
                            color: 'var(--accent-green)'
                        }}>
                            {logs.lines.length > 0 ? (
                                logs.lines.map((line, idx) => (
                                    <div key={idx} style={{
                                        whiteSpace: 'pre-wrap',
                                        wordBreak: 'break-all',
                                        color: line.includes('ERROR') ? 'var(--accent-red)' :
                                            line.includes('WARNING') ? 'var(--accent-orange)' :
                                                line.includes('SUCCESS') || line.includes('✓') ? 'var(--accent-green)' :
                                                    'var(--text-secondary)'
                                    }}>
                                        {line}
                                    </div>
                                ))
                            ) : (
                                <div style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>{LABELS.monitor.logs.noLogs}</div>
                            )}
                        </div>

                        {/* Modal Footer */}
                        <div style={{ marginTop: '1rem', fontSize: '0.75rem', color: 'var(--text-secondary)', textAlign: 'right' }}>
                            {LABELS.monitor.lastUpdate}: {new Date(logs.timestamp).toLocaleString()}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default TrainingMonitor;
