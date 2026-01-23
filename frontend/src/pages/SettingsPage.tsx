import React from 'react';
import { useConfig, type Metric } from '../context/ConfigContext';
import { useNavigate } from 'react-router-dom';

const SettingsPage: React.FC = () => {
    const { metrics, toggleMetric } = useConfig();
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

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {renderToggle('rain', 'Rainfall Prediction', '🌧️')}
                {renderToggle('temp', 'Temperature', '🌡️')}
                {renderToggle('hum', 'Humidity', '💧')}
            </div>
        </div>
    );
};

export default SettingsPage;
