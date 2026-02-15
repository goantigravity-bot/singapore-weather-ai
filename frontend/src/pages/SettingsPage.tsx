import React from 'react';
import { useConfig, type Metric, type GeocodingProvider } from '../context/ConfigContext';
import { useNavigate } from 'react-router-dom';
import { LABELS } from '../i18n/labels';

const SettingsPage: React.FC = () => {
    const { metrics, toggleMetric, showTriangle, toggleShowTriangle, showStations, toggleShowStations, showWind, toggleShowWind, showCloud, toggleShowCloud, geocodingProvider, setGeocodingProvider, psiThreshold, setPsiThreshold } = useConfig();
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
                        {isActive ? LABELS.settings.visible : LABELS.settings.hidden}
                    </div>
                </div>
                <div style={{ alignSelf: 'center', fontSize: '1.5rem', color: isActive ? 'var(--accent-green)' : 'gray' }}>
                    {isActive ? '☑' : '☐'}
                </div>
            </div>
        );
    };

    // PSI 阈值对应的 NEA 等级颜色
    const getPsiColor = (psi: number) => {
        if (psi <= 50) return '#4CAF50';
        if (psi <= 100) return '#2196F3';
        if (psi <= 200) return '#FF9800';
        if (psi <= 300) return '#F44336';
        return '#880E4F';
    };

    const getPsiLabel = (psi: number) => {
        if (psi <= 50) return 'Good';
        if (psi <= 100) return 'Moderate';
        if (psi <= 200) return 'Unhealthy';
        if (psi <= 300) return 'Very Unhealthy';
        return 'Hazardous';
    };

    const renderProviderCard = (provider: GeocodingProvider, label: string, desc: string, icon: string) => {
        const isActive = geocodingProvider === provider;
        return (
            <div
                className="metric-card"
                style={{
                    cursor: 'pointer',
                    borderColor: isActive ? 'var(--accent-cyan)' : 'transparent',
                    opacity: isActive ? 1 : 0.6,
                    flex: 1,
                }}
                onClick={() => setGeocodingProvider(provider)}
            >
                <div className="metric-icon">{icon}</div>
                <div className="metric-info">
                    <div className="metric-label">{label}</div>
                    <div className="metric-value" style={{ fontSize: '0.85rem', color: isActive ? 'var(--accent-cyan)' : 'gray' }}>
                        {desc}
                    </div>
                </div>
                <div style={{ alignSelf: 'center', fontSize: '1.5rem', color: isActive ? 'var(--accent-green)' : 'gray' }}>
                    {isActive ? '●' : '○'}
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
                        ← {LABELS.common.backToHome}
                    </button>
                    <h2 style={{ margin: 0, color: 'var(--text-primary)', fontSize: '1.75rem' }}>{LABELS.settings.title}</h2>
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
                        {LABELS.settings.description}
                    </p>

                    {/* Metrics Grid */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
                        {renderToggle('rain', LABELS.settings.metrics.rain, '🌧️')}
                        {renderToggle('temp', LABELS.settings.metrics.temp, '🌡️')}
                        {renderToggle('hum', LABELS.settings.metrics.hum, '💧')}
                        {renderToggle('pm25', LABELS.settings.metrics.pm25, '😷')}
                    </div>

                    <hr style={{ width: '100%', borderColor: 'rgba(255,255,255,0.1)', margin: '1.5rem 0' }} />

                    {/* Haze Alert Threshold */}
                    <h4 style={{ color: 'var(--text-primary)', marginBottom: '0.5rem' }}>🌫️ {LABELS.settings.hazeAlert.title}</h4>
                    <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem' }}>
                        {LABELS.settings.hazeAlert.description}
                    </p>
                    <div className="metric-card" style={{ flexDirection: 'column', gap: '12px', padding: '16px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                            <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>PSI Threshold</span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{
                                    fontSize: '1.4rem',
                                    fontWeight: 700,
                                    color: getPsiColor(psiThreshold),
                                }}>{psiThreshold}</span>
                                <span style={{
                                    fontSize: '0.8rem',
                                    color: getPsiColor(psiThreshold),
                                    padding: '2px 8px',
                                    borderRadius: '12px',
                                    background: `${getPsiColor(psiThreshold)}22`,
                                }}>{getPsiLabel(psiThreshold)}</span>
                            </div>
                        </div>
                        <input
                            type="range"
                            min={0} max={300} step={10}
                            value={psiThreshold}
                            onChange={(e) => setPsiThreshold(Number(e.target.value))}
                            style={{
                                width: '100%',
                                accentColor: getPsiColor(psiThreshold),
                                cursor: 'pointer',
                            }}
                        />
                        {/* NEA 参考色带 */}
                        <div style={{ display: 'flex', width: '100%', borderRadius: '4px', overflow: 'hidden', height: '6px' }}>
                            <div style={{ flex: 50, background: '#4CAF50' }} title="Good (0-50)" />
                            <div style={{ flex: 50, background: '#2196F3' }} title="Moderate (51-100)" />
                            <div style={{ flex: 100, background: '#FF9800' }} title="Unhealthy (101-200)" />
                            <div style={{ flex: 100, background: '#F44336' }} title="Very Unhealthy (201-300)" />
                        </div>
                    </div>

                    <hr style={{ width: '100%', borderColor: 'rgba(255,255,255,0.1)', margin: '1.5rem 0' }} />

                    {/* Map Options */}
                    <h4 style={{ color: 'var(--text-primary)', marginBottom: '1rem' }}>{LABELS.settings.mapOptions}</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                        {/* Interpolation Triangle Toggle */}
                        <div
                            className="metric-card"
                            style={{ cursor: 'pointer', borderColor: showTriangle ? 'var(--accent-orange)' : 'transparent', opacity: showTriangle ? 1 : 0.6 }}
                            onClick={toggleShowTriangle}
                        >
                            <div className="metric-icon">📐</div>
                            <div className="metric-info">
                                <div className="metric-label">{LABELS.settings.toggles.triangle}</div>
                                <div className="metric-value" style={{ fontSize: '1rem', color: showTriangle ? 'var(--accent-orange)' : 'gray' }}>
                                    {showTriangle ? LABELS.settings.visible : LABELS.settings.hidden}
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
                                <div className="metric-label">{LABELS.settings.toggles.stations}</div>
                                <div className="metric-value" style={{ fontSize: '1rem', color: showStations ? 'var(--accent-purple)' : 'gray' }}>
                                    {showStations ? LABELS.settings.visible : LABELS.settings.hidden}
                                </div>
                            </div>
                            <div style={{ alignSelf: 'center', fontSize: '1.5rem', color: showStations ? 'var(--accent-green)' : 'gray' }}>
                                {showStations ? '☑' : '☐'}
                            </div>
                        </div>

                        {/* Wind Direction Arrows Toggle */}
                        <div
                            className="metric-card"
                            style={{ cursor: 'pointer', borderColor: showWind ? 'var(--accent-cyan)' : 'transparent', opacity: showWind ? 1 : 0.6 }}
                            onClick={toggleShowWind}
                        >
                            <div className="metric-icon">🌬️</div>
                            <div className="metric-info">
                                <div className="metric-label">Wind Direction</div>
                                <div className="metric-value" style={{ fontSize: '1rem', color: showWind ? 'var(--accent-cyan)' : 'gray' }}>
                                    {showWind ? LABELS.settings.visible : LABELS.settings.hidden}
                                </div>
                            </div>
                            <div style={{ alignSelf: 'center', fontSize: '1.5rem', color: showWind ? 'var(--accent-green)' : 'gray' }}>
                                {showWind ? '☑' : '☐'}
                            </div>
                        </div>

                        {/* Satellite Cloud Layer Toggle */}
                        <div
                            className="metric-card"
                            style={{ cursor: 'pointer', borderColor: showCloud ? 'var(--accent-cyan)' : 'transparent', opacity: showCloud ? 1 : 0.6 }}
                            onClick={toggleShowCloud}
                        >
                            <div className="metric-icon">🛰️</div>
                            <div className="metric-info">
                                <div className="metric-label">{LABELS.settings.toggles.cloud}</div>
                                <div className="metric-value" style={{ fontSize: '1rem', color: showCloud ? 'var(--accent-cyan)' : 'gray' }}>
                                    {showCloud ? LABELS.settings.visible : LABELS.settings.hidden}
                                </div>
                            </div>
                            <div style={{ alignSelf: 'center', fontSize: '1.5rem', color: showCloud ? 'var(--accent-green)' : 'gray' }}>
                                {showCloud ? '☑' : '☐'}
                            </div>
                        </div>
                    </div>

                    <hr style={{ width: '100%', borderColor: 'rgba(255,255,255,0.1)', margin: '1.5rem 0' }} />

                    {/* Integration — Geocoding Provider */}
                    <h4 style={{ color: 'var(--text-primary)', marginBottom: '1rem' }}>🔌 {LABELS.settings.integration.title}</h4>
                    <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem', fontSize: '0.9rem' }}>
                        {LABELS.settings.integration.geocodingProvider}
                    </p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
                        {renderProviderCard('nominatim', LABELS.settings.integration.nominatim, LABELS.settings.integration.nominatimDesc, '🗺️')}
                        {renderProviderCard('onemap', LABELS.settings.integration.onemap, LABELS.settings.integration.onemapDesc, '🇸🇬')}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SettingsPage;

