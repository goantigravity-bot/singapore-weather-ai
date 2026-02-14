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
        psi: number | null;
    };
}

interface Props {
    data: ForecastData | null;
    loading: boolean;
    error: string | null;
}

const ForecastPanel: React.FC<Props> = ({ data, loading, error }) => {
    const { metrics, psiThreshold } = useConfig();
    const [isMinimized, setIsMinimized] = React.useState(true);

    // PSI 按 NEA 标准返回对应颜色
    const getPsiColor = (psi: number) => {
        if (psi <= 50) return '#4CAF50';
        if (psi <= 100) return '#2196F3';
        if (psi <= 200) return '#FF9800';
        if (psi <= 300) return '#F44336';
        return '#880E4F';
    };

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

    // EXPANDED: Card-based Display
    return (
        <div style={{
            position: 'absolute',
            bottom: '30px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 1000,
            width: '90%',
            maxWidth: '400px', // Slightly narrower for a card look
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            pointerEvents: 'none'
        }}>
            <div style={{
                pointerEvents: 'auto',
                background: 'rgba(20, 20, 20, 0.85)', // Darker, less transparent background for readability
                backdropFilter: 'blur(16px)',
                borderRadius: '24px', // More standard card radius
                border: '1px solid rgba(255, 255, 255, 0.1)',
                padding: '20px',
                display: 'flex',
                flexDirection: 'column',
                gap: '16px',
                boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
                color: 'white',
                width: '100%',
                boxSizing: 'border-box'
            }}>
                {/* 1. Header Section: Location & Time */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <h2 style={{
                            margin: 0,
                            fontSize: '1.4rem',
                            fontWeight: 700,
                            textShadow: '0 2px 4px rgba(0,0,0,0.5)',
                            lineHeight: 1.2
                        }}>
                            {data.nearest_station.name}
                        </h2>
                        <span style={{
                            fontSize: '0.85rem',
                            color: 'rgba(255,255,255,0.7)',
                            fontWeight: 500
                        }}>
                            {new Date(data.timestamp).toLocaleString(undefined, {
                                weekday: 'short',
                                day: 'numeric',
                                month: 'short',
                                hour: 'numeric',
                                minute: '2-digit'
                            })}
                        </span>
                    </div>
                    {/* Close Button */}
                    <button
                        onClick={() => setIsMinimized(true)}
                        style={{
                            background: 'rgba(255,255,255,0.1)',
                            border: 'none',
                            borderRadius: '50%',
                            width: '28px',
                            height: '28px',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: 'white',
                            cursor: 'pointer',
                            fontSize: '0.9rem'
                        }}
                    >
                        ✕
                    </button>
                </div>

                {/* Divider */}
                <div style={{ width: '100%', height: '1px', background: 'rgba(255,255,255,0.1)' }}></div>

                {/* 2. Recommendation Banner — waterfall: rain → PSI → recommended */}
                {(() => {
                    const isRain = data.forecast.description.includes("Rain") || data.forecast.description.includes("Storm");
                    const psi = data.current_weather?.psi;
                    const psiExceedsThreshold = psi != null && psi > psiThreshold;

                    if (isRain) {
                        return (
                            <div style={{
                                display: 'flex', alignItems: 'center', gap: '12px', padding: '12px',
                                borderRadius: '16px',
                                background: 'rgba(255, 87, 87, 0.15)',
                                border: '1px solid rgba(255, 87, 87, 0.3)'
                            }}>
                                <span style={{ fontSize: '1.8rem' }}>🌧️</span>
                                <div style={{ display: 'flex', flexDirection: 'column' }}>
                                    <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Recommendation</span>
                                    <span style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--accent-red)' }}>Not Recommended</span>
                                </div>
                                <span style={{ marginLeft: 'auto', fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)' }}>Rain expected</span>
                            </div>
                        );
                    }

                    if (psiExceedsThreshold) {
                        return (
                            <div style={{
                                display: 'flex', alignItems: 'center', gap: '12px', padding: '12px',
                                borderRadius: '16px',
                                background: 'rgba(255, 152, 0, 0.15)',
                                border: '1px solid rgba(255, 152, 0, 0.3)'
                            }}>
                                <span style={{ fontSize: '1.8rem' }}>🌫️</span>
                                <div style={{ display: 'flex', flexDirection: 'column' }}>
                                    <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Recommendation</span>
                                    <span style={{ fontSize: '1.1rem', fontWeight: 600, color: '#FF9800' }}>Not Recommended</span>
                                </div>
                                <span style={{ marginLeft: 'auto', fontWeight: 600, color: getPsiColor(psi!) }}>PSI: {psi}</span>
                            </div>
                        );
                    }

                    // Recommended
                    return (
                        <div style={{
                            display: 'flex', alignItems: 'center', gap: '12px', padding: '12px',
                            borderRadius: '16px',
                            background: 'rgba(75, 255, 120, 0.1)',
                            border: '1px solid rgba(75, 255, 120, 0.3)'
                        }}>
                            <span style={{ fontSize: '1.8rem' }}>✅</span>
                            <div style={{ display: 'flex', flexDirection: 'column' }}>
                                <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Recommendation</span>
                                <span style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--accent-green)' }}>Recommended</span>
                            </div>
                            {psi != null && (
                                <span style={{ marginLeft: 'auto', fontWeight: 600, color: getPsiColor(psi) }}>PSI: {psi}</span>
                            )}
                        </div>
                    );
                })()}

                {/* 3. Metrics Grid */}
                <div style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: '12px'
                }}>
                    {/* Temp */}
                    {metrics.has('temp') && (
                        <div style={{
                            background: 'rgba(255,255,255,0.05)',
                            padding: '12px',
                            borderRadius: '16px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '4px'
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)' }}>
                                <span>🌡️</span> Temp
                            </div>
                            <span style={{ fontSize: '1.2rem', fontWeight: 600, color: 'white' }}>
                                {data.current_weather?.temperature != null ? `${data.current_weather.temperature}°C` : "--"}
                            </span>
                        </div>
                    )}

                    {/* Humidity */}
                    {metrics.has('hum') && (
                        <div style={{
                            background: 'rgba(255,255,255,0.05)',
                            padding: '12px',
                            borderRadius: '16px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '4px'
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)' }}>
                                <span>💧</span> Humidity
                            </div>
                            <span style={{ fontSize: '1.2rem', fontWeight: 600, color: 'white' }}>
                                {data.current_weather?.humidity != null ? `${data.current_weather.humidity}%` : "--"}
                            </span>
                        </div>
                    )}

                    {/* PM2.5 */}
                    {metrics.has('pm25') && (
                        <div style={{
                            background: 'rgba(255,255,255,0.05)',
                            padding: '12px',
                            borderRadius: '16px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '4px'
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)' }}>
                                <span>😷</span> PM2.5
                            </div>
                            <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
                                <span style={{ fontSize: '1.2rem', fontWeight: 600, color: 'white' }}>
                                    {data.current_weather?.pm25 != null ? `${data.current_weather.pm25}` : "--"}
                                </span>
                                <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)' }}>µg</span>
                            </div>
                        </div>
                    )}

                    {/* PSI — 颜色按 NEA 标准 */}
                    {data.current_weather?.psi != null && (
                        <div style={{
                            background: 'rgba(255,255,255,0.05)',
                            padding: '12px',
                            borderRadius: '16px',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '4px'
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)' }}>
                                <span>🌫️</span> PSI
                            </div>
                            <span style={{ fontSize: '1.2rem', fontWeight: 600, color: getPsiColor(data.current_weather.psi) }}>
                                {data.current_weather.psi}
                            </span>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default ForecastPanel;
