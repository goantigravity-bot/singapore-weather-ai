import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ConfigProvider, useConfig, type Metric } from '../context/ConfigContext';

// 在每个测试前清除 localStorage
beforeEach(() => {
    localStorage.clear();
});

describe('ConfigContext', () => {
    it('provides default metrics', () => {
        const wrapper = ({ children }: { children: React.ReactNode }) => (
            <ConfigProvider>{children}</ConfigProvider>
        );

        const { result } = renderHook(() => useConfig(), { wrapper });

        // 默认所有指标都开启
        expect(result.current.metrics.has('rain')).toBe(true);
        expect(result.current.metrics.has('temp')).toBe(true);
        expect(result.current.metrics.has('hum')).toBe(true);
        expect(result.current.metrics.has('pm25')).toBe(true);
    });

    it('toggles metric on/off', () => {
        const wrapper = ({ children }: { children: React.ReactNode }) => (
            <ConfigProvider>{children}</ConfigProvider>
        );

        const { result } = renderHook(() => useConfig(), { wrapper });

        // 初始状态 rain 是开启的
        expect(result.current.metrics.has('rain')).toBe(true);

        // 切换 rain 为关闭
        act(() => {
            result.current.toggleMetric('rain' as Metric);
        });

        expect(result.current.metrics.has('rain')).toBe(false);

        // 再次切换回开启
        act(() => {
            result.current.toggleMetric('rain' as Metric);
        });

        expect(result.current.metrics.has('rain')).toBe(true);
    });

    it('toggles showTriangle', () => {
        const wrapper = ({ children }: { children: React.ReactNode }) => (
            <ConfigProvider>{children}</ConfigProvider>
        );

        const { result } = renderHook(() => useConfig(), { wrapper });

        // 默认关闭
        expect(result.current.showTriangle).toBe(false);

        act(() => {
            result.current.toggleShowTriangle();
        });

        expect(result.current.showTriangle).toBe(true);
    });

    it('toggles showStations', () => {
        const wrapper = ({ children }: { children: React.ReactNode }) => (
            <ConfigProvider>{children}</ConfigProvider>
        );

        const { result } = renderHook(() => useConfig(), { wrapper });

        // 默认开启
        expect(result.current.showStations).toBe(true);

        act(() => {
            result.current.toggleShowStations();
        });

        expect(result.current.showStations).toBe(false);
    });

    it('persists metrics to localStorage', () => {
        const wrapper = ({ children }: { children: React.ReactNode }) => (
            <ConfigProvider>{children}</ConfigProvider>
        );

        const { result } = renderHook(() => useConfig(), { wrapper });

        act(() => {
            result.current.toggleMetric('rain' as Metric);
        });

        // 检查 localStorage 是否保存了配置
        const saved = localStorage.getItem('forecast_metrics');
        expect(saved).toBeTruthy();

        const parsed = JSON.parse(saved!);
        expect(parsed).not.toContain('rain');
    });
});
