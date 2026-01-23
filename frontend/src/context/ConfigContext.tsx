import React, { createContext, useContext, useEffect, useState } from 'react';

export type Metric = 'rain' | 'temp' | 'hum';

interface ConfigState {
    metrics: Set<Metric>;
    toggleMetric: (m: Metric) => void;
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
        return new Set<Metric>(['rain', 'temp', 'hum']); // Default all on
    });

    useEffect(() => {
        localStorage.setItem('forecast_metrics', JSON.stringify(Array.from(metrics)));
    }, [metrics]);

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

    return (
        <ConfigContext.Provider value={{ metrics, toggleMetric }}>
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
