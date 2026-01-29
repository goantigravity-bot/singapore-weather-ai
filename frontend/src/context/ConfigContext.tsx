import React, { createContext, useContext, useEffect, useState } from 'react';

export type Metric = 'rain' | 'temp' | 'hum' | 'pm25';

interface ConfigState {
    metrics: Set<Metric>;
    toggleMetric: (m: Metric) => void;
    showTriangle: boolean;
    toggleShowTriangle: () => void;
    showStations: boolean;
    toggleShowStations: () => void;
}

const ConfigContext = createContext<ConfigState | undefined>(undefined);

export const ConfigProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [metrics, setMetrics] = useState<Set<Metric>>(() => {
        // Load from local storage or default to rain only for clarity
        const saved = localStorage.getItem('forecast_metrics');
        if (saved) {
            try {
                const parsed = JSON.parse(saved);
                return new Set(parsed as Metric[]);
            } catch (e) {
                console.error("Failed to parse metrics", e);
            }
        }
        return new Set<Metric>(['rain', 'temp', 'hum', 'pm25']); // Default all on
    });

    const [showTriangle, setShowTriangle] = useState<boolean>(() => {
        const saved = localStorage.getItem('show_triangle');
        return saved ? JSON.parse(saved) : false;
    });

    const [showStations, setShowStations] = useState<boolean>(() => {
        const saved = localStorage.getItem('show_stations');
        return saved ? JSON.parse(saved) : true; // Default to showing stations
    });

    useEffect(() => {
        localStorage.setItem('forecast_metrics', JSON.stringify(Array.from(metrics)));
    }, [metrics]);

    useEffect(() => {
        localStorage.setItem('show_triangle', JSON.stringify(showTriangle));
    }, [showTriangle]);

    useEffect(() => {
        localStorage.setItem('show_stations', JSON.stringify(showStations));
    }, [showStations]);

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

    return (
        <ConfigContext.Provider value={{ metrics, toggleMetric, showTriangle, toggleShowTriangle, showStations, toggleShowStations }}>
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
