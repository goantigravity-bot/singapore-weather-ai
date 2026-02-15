import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';

export type Metric = 'rain' | 'temp' | 'hum' | 'pm25';
export type GeocodingProvider = 'nominatim' | 'onemap';

interface ConfigState {
    metrics: Set<Metric>;
    toggleMetric: (m: Metric) => void;
    showTriangle: boolean;
    toggleShowTriangle: () => void;
    showStations: boolean;
    toggleShowStations: () => void;
    showWind: boolean;
    toggleShowWind: () => void;
    showCloud: boolean;
    toggleShowCloud: () => void;
    geocodingProvider: GeocodingProvider;
    setGeocodingProvider: (p: GeocodingProvider) => void;
    psiThreshold: number;
    setPsiThreshold: (n: number) => void;
}

const ConfigContext = createContext<ConfigState | undefined>(undefined);

const API_BASE = import.meta.env.VITE_API_URL || '';

export const ConfigProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [metrics, setMetrics] = useState<Set<Metric>>(() => {
        const saved = localStorage.getItem('forecast_metrics');
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                return new Set(parsed as Metric[]);
            } catch (e) {
                console.error("Failed to parse metrics", e);
            }
        }
        return new Set<Metric>(['rain', 'temp', 'hum', 'pm25']);
    });

    const [showTriangle, setShowTriangle] = useState<boolean>(() => {
        const saved = localStorage.getItem('show_triangle');
        return saved ? JSON.parse(saved) : false;
    });

    const [showStations, setShowStations] = useState<boolean>(() => {
        const saved = localStorage.getItem('show_stations');
        return saved ? JSON.parse(saved) : true;
    });

    const [showWind, setShowWind] = useState<boolean>(() => {
        const saved = localStorage.getItem('show_wind');
        return saved ? JSON.parse(saved) : false;
    });

    const [showCloud, setShowCloud] = useState<boolean>(() => {
        const saved = localStorage.getItem('show_cloud');
        return saved ? JSON.parse(saved) : false;
    });

    const [geocodingProvider, setGeocodingProviderState] = useState<GeocodingProvider>(() => {
        const saved = localStorage.getItem('geocoding_provider');
        return (saved === 'onemap' ? 'onemap' : 'nominatim') as GeocodingProvider;
    });

    const [psiThreshold, setPsiThresholdState] = useState<number>(() => {
        const saved = localStorage.getItem('psi_threshold');
        return saved ? parseInt(saved, 10) : 50;
    });

    // 启动时从后端同步当前 provider 配置
    useEffect(() => {
        fetch(`${API_BASE}/api/config/geocoding`)
            .then(res => res.json())
            .then(data => {
                if (data.provider) {
                    setGeocodingProviderState(data.provider as GeocodingProvider);
                    localStorage.setItem('geocoding_provider', data.provider);
                }
            })
            .catch(() => { /* 静默失败，使用 localStorage 缓存值 */ });
    }, []);

    useEffect(() => {
        localStorage.setItem('forecast_metrics', JSON.stringify(Array.from(metrics)));
    }, [metrics]);

    useEffect(() => {
        localStorage.setItem('show_triangle', JSON.stringify(showTriangle));
    }, [showTriangle]);

    useEffect(() => {
        localStorage.setItem('show_stations', JSON.stringify(showStations));
    }, [showStations]);

    useEffect(() => {
        localStorage.setItem('show_wind', JSON.stringify(showWind));
    }, [showWind]);

    useEffect(() => {
        localStorage.setItem('show_cloud', JSON.stringify(showCloud));
    }, [showCloud]);

    const toggleMetric = (m: Metric) => {
        setMetrics(prev => {
            const next = new Set(prev);
            if (next.has(m)) {
                next.delete(m);
            } else {
                next.add(m);
            }
            return next;
        });
    };

    const toggleShowTriangle = () => {
        setShowTriangle(prev => !prev);
    };

    const toggleShowStations = () => {
        setShowStations(prev => !prev);
    };

    const toggleShowWind = () => {
        setShowWind(prev => !prev);
    };

    const toggleShowCloud = () => {
        setShowCloud(prev => !prev);
    };

    // 切换 provider 时同步到后端
    const setGeocodingProvider = useCallback((p: GeocodingProvider) => {
        setGeocodingProviderState(p);
        localStorage.setItem('geocoding_provider', p);
        fetch(`${API_BASE}/api/config/geocoding`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider: p }),
        }).catch(err => console.error('Failed to sync geocoding provider:', err));
    }, []);

    const setPsiThreshold = useCallback((n: number) => {
        setPsiThresholdState(n);
        localStorage.setItem('psi_threshold', String(n));
    }, []);

    return (
        <ConfigContext.Provider value={{
            metrics, toggleMetric,
            showTriangle, toggleShowTriangle,
            showStations, toggleShowStations,
            showWind, toggleShowWind,
            showCloud, toggleShowCloud,
            geocodingProvider, setGeocodingProvider,
            psiThreshold, setPsiThreshold,
        }}>
            {children}
        </ConfigContext.Provider>
    );
};

export const useConfig = () => {
    const context = useContext(ConfigContext);
    if (!context) {
        throw new Error("useConfig must be used within a ConfigProvider");
    }
    return context;
};
