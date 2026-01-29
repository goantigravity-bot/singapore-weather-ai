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
        <div className="dashboard-overlay" style={{ zIndex: 2000 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                <button onClick={() => navigate('/')} className="quick-link-chip" style={{ padding: '4px 8px' }}>
                    ←
                </button>
                <h3 style={{ margin: 0 }}>Configuration</h3>
            </div>

            <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>
                Select which weather metrics to display on the forecast panel.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                {renderToggle('rain', 'Rainfall Prediction', '🌧️')}
                {renderToggle('temp', 'Temperature', '🌡️')}
                {renderToggle('hum', 'Humidity', '💧')}
                {renderToggle('pm25', 'PM2.5 (Air Quality)', '😷')}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
                <hr style={{ width: '100%', borderColor: 'rgba(255,255,255,0.1)' }} />

                {/* Manual Visual Toggle for Triangle (Using similar style but referencing boolean directly) */}
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

                {/* Site Locations Toggle */}
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
    );
};

export default SettingsPage;
