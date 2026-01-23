import React, { useState } from 'react';

interface ForecastData {
    timestamp: string;
    location_query: string;
    nearest_station: {
        id: string;
        name: string;
    };
    forecast: {
        rainfall_mm_next_10min: number;
        description: string;
    };
    current_weather?: {
        temperature: number | null;
        humidity: number | null;
    };
}

interface Props {
    data: ForecastData | null;
    loading: boolean;
    error: string | null;
}

type Metric = 'rain' | 'temp' | 'hum';

const ForecastPanel: React.FC<Props> = ({ data, loading, error }) => {
    // Enable all by default or just rain
    const [metrics, setMetrics] = useState<Set<Metric>>(new Set(['rain']));

    const toggleMetric = (m: Metric) => {
        const newMetrics = new Set(metrics);
        if (newMetrics.has(m)) {
            newMetrics.delete(m);
        } else {
            newMetrics.add(m);
        }
        setMetrics(newMetrics);
    };

    if (loading) return <div className="dashboard-overlay"><h3>Loading...</h3></div>;
    if (error) return <div className="dashboard-overlay"><h3 style={{ color: 'var(--accent-red)' }}>Error: {error}</h3></div>;
    if (!data) return <div className="dashboard-overlay"><h3>Select a location directly on the map or search to see the forecast.</h3></div>;

    const isRain = data.forecast.description.includes("Rain") || data.forecast.description.includes("Storm");
    const statusColor = isRain ? "var(--accent-red)" : "var(--accent-green)";

    return (
        <div className="dashboard-overlay">
            <div className="status-badge">
                <div className="status-dot"></div>
                Live Status: Active
            </div>

            {/* Metric Selection Toggles (Checkboxes style) */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
                <button
                    onClick={() => toggleMetric('rain')}
                    className="quick-link-chip"
                    style={{
                        background: metrics.has('rain') ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.05)',
                        color: metrics.has('rain') ? '#000' : '#fff',
                        flex: 1, justifyContent: 'center'
                    }}
                >
                    {metrics.has('rain') ? '☑' : '☐'} Rain
                </button>
                <button
                    onClick={() => toggleMetric('temp')}
                    className="quick-link-chip"
                    style={{
                        background: metrics.has('temp') ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.05)',
                        color: metrics.has('temp') ? '#000' : '#fff',
                        flex: 1, justifyContent: 'center'
                    }}
                >
                    {metrics.has('temp') ? '☑' : '☐'} Temp
                </button>
                <button
                    onClick={() => toggleMetric('hum')}
                    className="quick-link-chip"
                    style={{
                        background: metrics.has('hum') ? 'var(--accent-cyan)' : 'rgba(255,255,255,0.05)',
                        color: metrics.has('hum') ? '#000' : '#fff',
                        flex: 1, justifyContent: 'center'
                    }}
                >
                    {metrics.has('hum') ? '☑' : '☐'} Hum
                </button>
            </div>

            <div>
                <div className="metric-label">Location</div>
                <div className="location-title">{data.nearest_station.name}</div>
                <div style={{ fontSize: '12px', color: 'gray' }}>Query: {data.location_query}</div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {metrics.has('rain') && (
                    <div className="metric-card" style={{ borderColor: statusColor }}>
                        <div className="metric-icon">
                            {isRain ? '🌧️' : '☁️'}
                        </div>
                        <div className="metric-info">
                            <div className="metric-label">Rainfall Prediction (10m)</div>
                            <div className="metric-value" style={{ color: statusColor }}>
                                {data.forecast.rainfall_mm_next_10min} mm
                            </div>
                            <div style={{ fontSize: '14px', color: statusColor }}>
                                {data.forecast.description}
                            </div>
                        </div>
                    </div>
                )}

                {metrics.has('temp') && (
                    <div className="metric-card">
                        <div className="metric-icon">🌡️</div>
                        <div className="metric-info">
                            <div className="metric-label">Current Temperature</div>
                            <div className="metric-value" style={{ color: "var(--accent-cyan)" }}>
                                {data.current_weather?.temperature != null ? `${data.current_weather.temperature} °C` : "N/A"}
                            </div>
                        </div>
                    </div>
                )}

                {metrics.has('hum') && (
                    <div className="metric-card">
                        <div className="metric-icon">💧</div>
                        <div className="metric-info">
                            <div className="metric-label">Relative Humidity</div>
                            <div className="metric-value" style={{ color: "var(--accent-cyan)" }}>
                                {data.current_weather?.humidity != null ? `${data.current_weather.humidity} %` : "N/A"}
                            </div>
                        </div>
                    </div>
                )}
            </div>

            <div className="metric-card" style={{ marginTop: '10px' }}>
                <div className="metric-icon">📡</div>
                <div className="metric-info">
                    <div className="metric-label">Nearest Sensor</div>
                    <div className="metric-value">{data.nearest_station.id}</div>
                </div>
            </div>

            <div style={{ fontSize: '10px', color: '#666', marginTop: 'auto' }}>
                Last Updated: {new Date(data.timestamp).toLocaleTimeString()}
            </div>
        </div>
    );
};

export default ForecastPanel;
