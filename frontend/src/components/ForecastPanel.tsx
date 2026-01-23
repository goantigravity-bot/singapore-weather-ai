import React from 'react';
import { useConfig } from '../context/ConfigContext';
import { Link } from 'react-router-dom';

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

const ForecastPanel: React.FC<Props> = ({ data, loading, error }) => {
    const { metrics } = useConfig();
    const [isMinimized, setIsMinimized] = React.useState(true);

    if (loading) return <div className="dashboard-overlay"><h3>Loading...</h3></div>;
    if (error) return <div className="dashboard-overlay"><h3 style={{ color: 'var(--accent-red)' }}>Error: {error}</h3></div>;
    if (!data) return <div className="dashboard-overlay"><h3>Select a location directly on the map or search to see the forecast.</h3></div>;

    const isRain = data.forecast.description.includes("Rain") || data.forecast.description.includes("Storm");
    const statusColor = isRain ? "var(--accent-red)" : "var(--accent-green)";

    // Minimized State: Just a small floating button
    if (isMinimized) {
        return (
            <div
                className="dashboard-overlay"
                style={{
                    height: 'auto',
                    padding: '0',
                    width: 'auto',
                    minWidth: 'auto',
                    background: 'transparent',
                    border: 'none',
                    boxShadow: 'none',
                    backdropFilter: 'none',
                    pointerEvents: 'none', // Let clicks pass through transparent area
                    bottom: '20px',
                    left: '50%',
                    transform: 'translateX(-50%)'
                }}
            >
                <div style={{ pointerEvents: 'auto' }}>
                    <button
                        onClick={() => setIsMinimized(false)}
                        className="quick-link-chip"
                        style={{
                            background: 'var(--panel-bg)',
                            border: '1px solid var(--accent-cyan)',
                            boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
                            padding: '10px 20px',
                            fontWeight: 'bold',
                            display: 'flex',
                            gap: '8px',
                            alignItems: 'center'
                        }}
                    >
                        <span>👀</span> Show Forecast
                    </button>
                </div>
            </div>
        );
    }

    return (
        <div className="dashboard-overlay">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <div className="status-badge">
                    <div className="status-dot"></div>
                    Live
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                        onClick={() => setIsMinimized(true)}
                        className="quick-link-chip"
                        style={{ padding: '4px 10px', fontSize: '1.2rem' }}
                        title="Hide Completely"
                    >
                        ➖
                    </button>
                    <Link to="/settings" className="quick-link-chip" style={{ padding: '4px 10px' }}>
                        ⚙️
                    </Link>
                </div>
            </div>

            {/* 1. Location Name on Top */}
            <div style={{ marginBottom: '20px' }}>
                <div className="location-title" style={{ fontSize: '1.5rem', fontWeight: 600 }}>
                    {data.nearest_station.name}
                </div>
            </div>

            {/* 3. Horizontal Metric Layout */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginBottom: '20px' }}>

                {/* Metric 1: Rain */}
                {metrics.has('rain') && (
                    <div className="metric-card" style={{ flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: '12px 4px', borderColor: statusColor }}>
                        <div style={{ fontSize: '1.5rem', marginBottom: '4px' }}>
                            {isRain ? '🌧️' : '☁️'}
                        </div>
                        <div style={{ fontSize: '0.8rem', color: '#aaa', marginBottom: '2px' }}>Rain</div>
                        <div style={{ fontSize: '0.9rem', fontWeight: 'bold', color: statusColor }}>
                            {isRain ? 'Yes' : 'No'}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: statusColor, marginTop: '2px' }}>
                            {data.forecast.rainfall_mm_next_10min} mm
                        </div>
                    </div>
                )}

                {/* Metric 2: Temperature */}
                {metrics.has('temp') && (
                    <div className="metric-card" style={{ flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: '12px 4px' }}>
                        <div style={{ fontSize: '1.5rem', marginBottom: '4px' }}>🌡️</div>
                        <div style={{ fontSize: '0.8rem', color: '#aaa', marginBottom: '2px' }}>Temperature</div>
                        <div style={{ fontSize: '1rem', color: "var(--accent-cyan)", fontWeight: 'bold' }}>
                            {data.current_weather?.temperature != null ? `${data.current_weather.temperature}°` : "N/A"}
                        </div>
                    </div>
                )}

                {/* Metric 3: Humidity */}
                {metrics.has('hum') && (
                    <div className="metric-card" style={{ flexDirection: 'column', alignItems: 'center', textAlign: 'center', padding: '12px 4px' }}>
                        <div style={{ fontSize: '1.5rem', marginBottom: '4px' }}>💧</div>
                        <div style={{ fontSize: '0.8rem', color: '#aaa', marginBottom: '2px' }}>Humidity</div>
                        <div style={{ fontSize: '1rem', color: "var(--accent-cyan)", fontWeight: 'bold' }}>
                            {data.current_weather?.humidity != null ? `${data.current_weather.humidity}%` : "N/A"}
                        </div>
                    </div>
                )}
            </div>

            {/* 4. Nearest Sensor at Bottom */}
            <div className="metric-card" style={{ marginTop: 'auto', background: 'rgba(255,255,255,0.03)' }}>
                <div className="metric-icon" style={{ fontSize: '1.2rem' }}>📡</div>
                <div className="metric-info">
                    <div className="metric-label">Sensor Site</div>
                    <div className="metric-value" style={{ fontSize: '0.9rem' }}>{data.nearest_station.id}</div>
                </div>
            </div>

            <div style={{ fontSize: '10px', color: '#666', marginTop: '10px', textAlign: 'center' }}>
                Updated: {new Date(data.timestamp).toLocaleTimeString()}
            </div>
        </div>
    );
};

export default ForecastPanel;
