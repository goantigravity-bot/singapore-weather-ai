// API 配置和请求函数

import type { OverviewStatus, DownloadStatus, TrainingStatus, SyncStatus, LogResponse } from './types';

// API 基础 URL - 使用 API 服务器直接地址
const API_BASE = import.meta.env.VITE_API_URL || 'http://3.0.28.161:8000/api';

async function fetchJson<T>(endpoint: string): Promise<T> {
    const response = await fetch(`${API_BASE}${endpoint}`);
    if (!response.ok) {
        throw new Error(`API Error: ${response.status}`);
    }
    return response.json();
}

export async function getOverview(): Promise<OverviewStatus> {
    return fetchJson<OverviewStatus>('/monitor/overview');
}

export async function getDownloadStatus(): Promise<DownloadStatus> {
    return fetchJson<DownloadStatus>('/monitor/download');
}

export async function getTrainingStatus(): Promise<TrainingStatus> {
    return fetchJson<TrainingStatus>('/monitor/training');
}

export async function getSyncStatus(): Promise<SyncStatus> {
    return fetchJson<SyncStatus>('/monitor/sync');
}

export async function getLogs(type: string, lines: number = 100): Promise<LogResponse> {
    return fetchJson<LogResponse>(`/monitor/logs/${type}?lines=${lines}`);
}

// Mock 数据用于开发测试
export function getMockOverview(): OverviewStatus {
    return {
        currentStage: 'training',
        download: {
            currentDate: '2025-10-03',
            completedDays: 3,
            totalDays: 119,
            filesDownloaded: 855,
            parallelProcesses: 4,
            status: 'running',
            lastUpdate: new Date().toISOString(),
            dateProgress: []
        },
        training: {
            currentDate: '2025-10-01',
            completedBatches: 0,
            totalEpochs: 0,
            currentPhase: 'downloading',
            phases: [
                { name: '下载数据', status: 'running', progress: 65 },
                { name: '预处理', status: 'pending' },
                { name: '训练', status: 'pending' },
                { name: '同步模型', status: 'pending' }
            ],
            diskUsage: '93 GB / 194 GB',
            status: 'running',
            lastUpdate: new Date().toISOString(),
            history: []
        },
        sync: {
            modelSynced: true,
            sensorDataSynced: false,
            lastSyncTime: '2026-01-28 01:10:03',
            status: 'ok'
        }
    };
}
