// 监控仪表盘 API 类型定义

export interface DownloadStatus {
    currentDate: string | null;
    completedDays: number;
    totalDays: number;
    filesDownloaded: number;
    parallelProcesses: number;
    status: 'running' | 'idle' | 'error' | 'completed';
    lastUpdate: string | null;
}

export interface TrainingPhase {
    name: string;
    status: 'pending' | 'running' | 'completed' | 'error';
    progress?: number;
    message?: string;
}

export interface TrainingStatus {
    currentDate: string | null;
    completedBatches: number;
    totalEpochs: number;
    currentPhase: string;
    phases: TrainingPhase[];
    diskUsage: string | null;
    status: 'running' | 'idle' | 'error' | 'waiting';
    lastUpdate: string | null;
}

export interface SyncStatus {
    modelSynced: boolean;
    sensorDataSynced: boolean;
    lastSyncTime: string | null;
    status: 'ok' | 'error' | 'unknown';
}

export interface OverviewStatus {
    currentStage: 'download' | 'training' | 'sync' | 'idle' | 'unknown';
    download: DownloadStatus;
    training: TrainingStatus;
    sync: SyncStatus;
}

export interface LogResponse {
    type: string;
    source?: string;
    path?: string;
    message?: string;
    lines: string[];
    timestamp: string;
}
