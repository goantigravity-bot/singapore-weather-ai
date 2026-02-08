import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import TrainingMonitor from '../pages/TrainingMonitor';

// Mock fetch API
const mockFetch = vi.fn();
globalThis.fetch = mockFetch as any;

const renderWithRouter = (component: React.ReactElement) => {
    return render(
        <BrowserRouter>
            {component}
        </BrowserRouter>
    );
};

// 模拟 API 响应数据
const mockOverviewData = {
    currentStage: 'download',
    download: {
        currentDate: '2025-10-15',
        completedDays: 9,
        totalDays: 119,
        filesDownloaded: 1330,
        status: 'running',
        lastUpdate: new Date().toISOString(),
        dateProgress: [
            { date: '2025-10-06', satelliteFiles: 141, satelliteTotal: 141, neaFiles: 4, neaTotal: 4, status: 'completed' },
            { date: '2025-10-07', satelliteFiles: 141, satelliteTotal: 141, neaFiles: 4, neaTotal: 4, status: 'completed' }
        ]
    },
    training: {
        currentDate: '2025-10-05',
        completedBatches: 5,
        totalEpochs: 400,
        currentPhase: 'idle',
        phases: [
            { name: '下载数据', status: 'completed' },
            { name: '预处理', status: 'completed' },
            { name: '训练', status: 'completed' },
            { name: '同步模型', status: 'pending' }
        ],
        status: 'idle',
        lastUpdate: new Date().toISOString(),
        history: [
            { id: 1, timestamp: '2025-01-28T10:00:00Z', dateRange: '2025-10-01 ~ 2025-10-05', epochs: 400, duration: '2h 30m', mae: 0.0416, rmse: 0.0625, success: true }
        ]
    },
    sync: {
        modelSynced: true,
        sensorDataSynced: true,
        lastSyncTime: '2025-01-28 01:10:03',
        status: 'ok'
    }
};

describe('TrainingMonitor', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockFetch.mockResolvedValue({
            ok: true,
            json: () => Promise.resolve(mockOverviewData)
        });
    });

    it('shows loading state initially', () => {
        mockFetch.mockImplementation(() => new Promise(() => { })); // Never resolves
        renderWithRouter(<TrainingMonitor />);
        expect(screen.getByText('Loading Monitor...')).toBeInTheDocument();
    });

    it('renders page title after loading', async () => {
        renderWithRouter(<TrainingMonitor />);

        await waitFor(() => {
            expect(screen.getByText('系统监控仪表盘')).toBeInTheDocument();
        });
    });

    it('renders three tabs', async () => {
        renderWithRouter(<TrainingMonitor />);

        await waitFor(() => {
            expect(screen.getByText('文件下载')).toBeInTheDocument();
            expect(screen.getByText('训练流程')).toBeInTheDocument();
            expect(screen.getByText('API 应用')).toBeInTheDocument();
        });
    });

    it('renders back button', async () => {
        renderWithRouter(<TrainingMonitor />);

        await waitFor(() => {
            expect(screen.getByText('← 返回')).toBeInTheDocument();
        });
    });

    it('renders view logs button', async () => {
        renderWithRouter(<TrainingMonitor />);

        await waitFor(() => {
            expect(screen.getByText('📋 查看日志')).toBeInTheDocument();
        });
    });

    it('renders download progress on default tab', async () => {
        renderWithRouter(<TrainingMonitor />);

        await waitFor(() => {
            expect(screen.getByText('已完成天数')).toBeInTheDocument();
            expect(screen.getByText('总文件数')).toBeInTheDocument();
            expect(screen.getByText('当前日期')).toBeInTheDocument();
        });
    });

    it('renders download stats values', async () => {
        renderWithRouter(<TrainingMonitor />);

        await waitFor(() => {
            expect(screen.getByText('9/119')).toBeInTheDocument();
            expect(screen.getByText('1,330')).toBeInTheDocument();
        });
    });

    it('renders date progress table', async () => {
        renderWithRouter(<TrainingMonitor />);

        await waitFor(() => {
            expect(screen.getByText('每日下载详情')).toBeInTheDocument();
            expect(screen.getByText('卫星数据')).toBeInTheDocument();
            expect(screen.getByText('NEA 数据')).toBeInTheDocument();
        });
    });

    it('shows error state on API failure', async () => {
        mockFetch.mockRejectedValueOnce(new Error('Network error'));

        renderWithRouter(<TrainingMonitor />);

        await waitFor(() => {
            expect(screen.getByText(/Failed to load/)).toBeInTheDocument();
        });
    });
});
