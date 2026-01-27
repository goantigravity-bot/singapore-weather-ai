import React from 'react';
import { useConfig } from '../context/ConfigContext';

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
        pm25: number | null;
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

    if (loading) return <div className="dashboard-overlay" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)', width: 'auto', textAlign: 'center' }}>Loading...</div>;
    if (error) return <div className="dashboard-overlay" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)', width: 'auto' }}><span style={{ color: 'var(--accent-red)' }}>Error: {error}</span></div>;

    // Initial State (No Data)
    if (!data) {
        return (
            <div className="dashboard-overlay" style={{
                background: 'rgba(0,0,0,0.3)',
                backdropFilter: 'blur(4px)',
                width: 'auto',
                padding: '10px 20px',
                borderRadius: '30px',
                border: '1px solid rgba(255,255,255,0.1)'
            }}>
                <span style={{ fontSize: '0.9rem', color: '#ddd' }}>Select a location on the map</span>
            </div>
        );
    }

    const isRain = data.forecast.description.includes("Rain") || data.forecast.description.includes("Storm");
    const statusColor = isRain ? "var(--accent-red)" : "var(--accent-green)";

    // Minimized State: Just a small floating button (Optional, but user might still want to hide it completely)
    if (isMinimized) {
        return (
            <div style={{
                position: 'absolute',
                bottom: '20px',
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 1000,
                pointerEvents: 'auto'
            }}>
                <button
                    onClick={() => setIsMinimized(false)}
                    className="quick-link-chip"
                    style={{
                        background: 'rgba(0, 0, 0, 0.6)',
                        backdropFilter: 'blur(8px)',
                        border: '1px solid rgba(255, 255, 255, 0.15)',
                        padding: '8px 20px',
                        borderRadius: '30px',
                        color: 'white',
                        fontWeight: 'bold',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        boxShadow: '0 4px 15px rgba(0,0,0,0.3)'
                    }}
                >
                    <span>👀</span> Show Forecast
                </button>
            </div>
        );
    }

    // EXPANDED: Compact "Heads-Up" Display
    return (
        <div style={{
            position: 'absolute',
            bottom: '30px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 1000,
            width: '90%',
            maxWidth: '600px', // Prevent being too wide on desktop
            display: 'flex',
            flexDirection: 'column', // Allow updated time to sit below or nice layout
            alignItems: 'center',
            pointerEvents: 'none' // Wrapper checks events, internal needs auto
        }}>
            <div style={{
                pointerEvents: 'auto',
                background: 'rgba(20, 20, 20, 0.65)', // Semi-transparent dark
                backdropFilter: 'blur(12px)',
                borderRadius: '50px', // Pill shape
                border: '1px solid rgba(255, 255, 255, 0.1)',
                padding: '12px 24px',
                display: 'flex',
                alignItems: 'center',
                gap: '20px',
                boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
                color: 'white',
                whiteSpace: 'nowrap'
            }}>
                {/* 1. Location Name */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '1.2rem' }}>📍</span>
                    <span style={{ fontSize: '1.1rem', fontWeight: 700, textShadow: '0 2px 4px rgba(0,0,0,0.5)' }}>
                        {data.nearest_station.name}
                    </span>
                </div>

                {/* Vertical Divider */}
                <div style={{ width: '1px', height: '24px', background: 'rgba(255,255,255,0.2)' }}></div>

                {/* 2. Metrics Row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                    {/* Rain */}
                    {metrics.has('rain') && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }} title={`Rainfall: ${data.forecast.rainfall_mm_next_10min}mm`}>
                            <span style={{ fontSize: '1.2rem' }}>{isRain ? '🌧️' : '☁️'}</span>
                            <span style={{ fontWeight: 600, color: statusColor }}>
                                {isRain ? 'Rain' : 'Clear'}
                            </span>
                        </div>
                    )}

                    {/* Temp */}
                    {metrics.has('temp') && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ fontSize: '1.2rem' }}>🌡️</span>
                            <span style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>
                                {data.current_weather?.temperature != null ? `${data.current_weather.temperature}°` : "--"}
                            </span>
                        </div>
                    )}

                    {/* Humidity */}
                    {metrics.has('hum') && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ fontSize: '1.2rem' }}>💧</span>
                            <span style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>
                                {data.current_weather?.humidity != null ? `${data.current_weather.humidity}%` : "--"}
                            </span>
                        </div>
                    )}

                    {/* PM2.5 */}
                    {metrics.has('pm25') && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ fontSize: '1.2rem' }}>😷</span>
                            <span style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>
                                {data.current_weather?.pm25 != null ? `${data.current_weather.pm25}` : "--"}
                            </span>
                            <span style={{ fontSize: '0.8rem', opacity: 0.7 }}>µg</span>
                        </div>
                    )}
                </div>

                {/* Close/Minimize Button (Small X at end) */}
                <div style={{ marginLeft: 'auto', paddingLeft: '10px' }}>
                    <button
                        onClick={() => setIsMinimized(true)}
                        style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer', fontSize: '1rem', padding: '4px' }}
                    >
                        ✕
                    </button>
                </div>
            </div>

            {/* Tiny Updated Timestamp Below */}
            <div style={{
                marginTop: '6px',
                fontSize: '0.75rem',
                color: 'rgba(255,255,255,0.8)',
                textShadow: '0 1px 2px rgba(0,0,0,0.8)',
                background: 'rgba(0,0,0,0.3)',
                padding: '2px 8px',
                borderRadius: '10px'
            }}>
                Updated: {new Date(data.timestamp).toLocaleString()}
            </div>
        </div>
    );
};

export default ForecastPanel;
