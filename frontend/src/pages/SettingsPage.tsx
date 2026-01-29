import React from 'react';
import { useConfig, type Metric } from '../context/ConfigContext';
import { useNavigate } from 'react-router-dom';

const SettingsPage: React.FC = () => {
    const { metrics, toggleMetric, showTriangle, toggleShowTriangle, showStations, toggleShowStations } = useConfig();
    const navigate = useNavigate();

    const renderToggle = (metric: Metric, label: string, icon: string) => {
        const isActive = metrics.has(metric);
        return (
            <div
                className="metric-card"
                style={{ cursor: 'pointer', borderColor: isActive ? 'var(--accent-cyan)' : 'transparent', opacity: isActive ? 1 : 0.6 }}
                onClick={() => toggleMetric(metric)}
            >
                <div className="metric-icon">{icon}</div>
                <div className="metric-info">
                    <div className="metric-label">{label}</div>
                    <div className="metric-value" style={{ fontSize: '1rem', color: isActive ? 'var(--accent-cyan)' : 'gray' }}>
                        {isActive ? 'Visible' : 'Hidden'}
                    </div>
                </div>
                <div style={{ alignSelf: 'center', fontSize: '1.5rem', color: isActive ? 'var(--accent-green)' : 'gray' }}>
                    {isActive ? '☑' : '☐'}
                </div>
            </div>
        );
    };

    return (
        <div style={{
            width: '100%',
            minHeight: '100vh',
            background: 'var(--bg-color)',
            padding: '2rem',
            boxSizing: 'border-box',
            overflow: 'auto'
        }}>
            <div style={{ maxWidth: '800px', margin: '0 auto' }}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
                    <button onClick={() => navigate('/')} className="quick-link-chip" style={{ padding: '8px 16px' }}>
                        ← 返回
                    </button>
                    <h2 style={{ margin: 0, color: 'var(--text-primary)', fontSize: '1.75rem' }}>Configuration</h2>
                </div>

                {/* Content Panel */}
                <div style={{
                    background: 'var(--panel-bg)',
                    backdropFilter: 'blur(12px)',
                    borderRadius: '16px',
                    padding: '2rem',
                    border: '1px solid var(--panel-border)'
                }}>
                    <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', fontSize: '1rem' }}>
                        Select which weather metrics to display on the forecast panel.
                    </p>

                    {/* Metrics Grid */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                        {renderToggle('rain', 'Rainfall Prediction', '🌧️')}
                        {renderToggle('temp', 'Temperature', '🌡️')}
                        {renderToggle('hum', 'Humidity', '💧')}
                        {renderToggle('pm25', 'PM2.5 (Air Quality)', '😷')}
                    </div>

                    <hr style={{ width: '100%', borderColor: 'rgba(255,255,255,0.1)', margin: '1.5rem 0' }} />

                    {/* Map Options */}
                    <h4 style={{ color: 'var(--text-primary)', marginBottom: '1rem' }}>Map Display Options</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        {/* Interpolation Triangle Toggle */}
                        <div
                            className="metric-card"
                            style={{ cursor: 'pointer', borderColor: showTriangle ? 'var(--accent-orange)' : 'transparent', opacity: showTriangle ? 1 : 0.6 }}
                            onClick={toggleShowTriangle}
                        >
                            <div className="metric-icon">📐</div>
                            <div className="metric-info">
                                <div className="metric-label">Interpolation Triangle</div>
                                <div className="metric-value" style={{ fontSize: '1rem', color: showTriangle ? 'var(--accent-orange)' : 'gray' }}>
                                    {showTriangle ? 'Visible' : 'Hidden'}
                                </div>
                            </div>
                            <div style={{ alignSelf: 'center', fontSize: '1.5rem', color: showTriangle ? 'var(--accent-green)' : 'gray' }}>
                                {showTriangle ? '☑' : '☐'}
                            </div>
                        </div>

                        {/* Weather Station Markers Toggle */}
                        <div
                            className="metric-card"
                            style={{ cursor: 'pointer', borderColor: showStations ? 'var(--accent-purple)' : 'transparent', opacity: showStations ? 1 : 0.6 }}
                            onClick={toggleShowStations}
                        >
                            <div className="metric-icon">📍</div>
                            <div className="metric-info">
                                <div className="metric-label">Weather Station Markers</div>
                                <div className="metric-value" style={{ fontSize: '1rem', color: showStations ? 'var(--accent-purple)' : 'gray' }}>
                                    {showStations ? 'Visible' : 'Hidden'}
                                </div>
                            </div>
                            <div style={{ alignSelf: 'center', fontSize: '1.5rem', color: showStations ? 'var(--accent-green)' : 'gray' }}>
                                {showStations ? '☑' : '☐'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SettingsPage;
