import React, { useEffect, useState } from 'react';
import { API_BASE_URL } from '../config';

// Types based on our backend JSON
interface TrainingStatus {
    status: 'active' | 'idle' | 'completed' | 'failed' | 'unknown';
    current_batch: number;
    total_batches: number;
    current_step: string;
    batch_start: string;
    batch_end: string;
    last_updated: string;
    error?: string;
}

interface TrainingRun {
    id: number;
    timestamp: string;
    duration_formatted: string;
    success: boolean;
    metrics: {
        mae: number;
        rmse: number;
        accuracy: number;
    };
    data_info: {
        date_range: string;
        sensor_records: number;
    }
}

const TrainingMonitor: React.FC = () => {
    const [status, setStatus] = useState<TrainingStatus | null>(null);
    const [history, setHistory] = useState<TrainingRun[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchData = async () => {
        try {
            // Use centralized config
            const statusRes = await fetch(`${API_BASE_URL}/training/status`);
            const statusData = await statusRes.json();
            setStatus(statusData);

            const historyRes = await fetch(`${API_BASE_URL}/training/history`);
            const historyData = await historyRes.json();
            setHistory(Array.isArray(historyData) ? historyData : []);
        } catch (err) {
            console.error("Failed to fetch training data", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 5000); // Poll every 5s
        return () => clearInterval(interval);
    }, []);

    if (loading && !status) return <div className="p-8 text-center">Loading Monitor...</div>;

    // Calculate Progress
    const pct = status?.status === 'active' || status?.status === 'completed'
        ? Math.round((status.current_batch / status.total_batches) * 100)
        : 0;

    return (
        <div className="max-w-7xl mx-auto px-16 py-10 space-y-10" style={{ marginTop: '100px', paddingLeft: '64px', paddingRight: '64px' }}>
            <h1 className="text-4xl font-bold text-white mb-2">
                训练监控
            </h1>

            {/* Status Card */}
            <div className="bg-gray-800/50 rounded-xl p-10 border border-gray-700 backdrop-blur-md shadow-xl">
                <div className="flex justify-between items-center mb-6">
                    <div>
                        <h2 className="text-2xl font-semibold text-white mb-3">当前状态</h2>
                        <span className={`inline-block px-4 py-2 rounded-full text-sm font-bold uppercase tracking-wider ${status?.status === 'active' ? 'bg-blue-500/20 text-blue-300 animate-pulse' :
                            status?.status === 'completed' ? 'bg-green-500/20 text-green-300' :
                                status?.status === 'failed' ? 'bg-red-500/20 text-red-300' :
                                    'bg-gray-600/20 text-gray-400'
                            }`}>
                            {status?.status || 'Unknown'}
                        </span>
                    </div>
                    <div className="text-right">
                        <div className="text-5xl font-mono font-bold text-white">{pct}%</div>
                        <div className="text-sm text-gray-400 mt-1">整体进度</div>
                    </div>
                </div>

                {/* Progress Bar */}
                <div className="w-full bg-gray-700 rounded-full h-5 mb-8 overflow-hidden shadow-inner">
                    <div
                        className="bg-gradient-to-r from-blue-500 to-teal-400 h-5 rounded-full transition-all duration-500 ease-out shadow-lg"
                        style={{ width: `${pct}%` }}
                    ></div>
                </div>

                {/* Details Grid */}
                {status && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
                        <div className="bg-gray-900/50 p-5 rounded-lg border border-gray-700/50">
                            <label className="block text-gray-400 text-xs uppercase mb-2 tracking-wide">当前活动</label>
                            <div className="text-white font-medium flex items-center gap-2 text-base">
                                {status.status === 'active' && <span className="w-2 h-2 bg-green-400 rounded-full animate-ping" />}
                                {status.current_step}
                            </div>
                        </div>
                        <div className="bg-gray-900/50 p-5 rounded-lg border border-gray-700/50">
                            <label className="block text-gray-400 text-xs uppercase mb-2 tracking-wide">批次进度</label>
                            <div className="text-white text-base">
                                批次 <span className="font-bold text-blue-300">{status.current_batch}</span> / {status.total_batches}
                            </div>
                            <div className="text-gray-500 text-xs mt-2">
                                {status.batch_start} → {status.batch_end}
                            </div>
                        </div>
                        {status.error && (
                            <div className="col-span-2 bg-red-900/30 border border-red-500/30 p-5 rounded-lg text-red-200">
                                <strong>错误:</strong> {status.error}
                            </div>
                        )}
                        <div className="col-span-2 text-right text-xs text-gray-500 mt-2">
                            最后更新: {new Date(status.last_updated).toLocaleString('zh-CN')}
                        </div>
                    </div>
                )}
            </div>

            {/* History Table */}
            <div className="bg-gray-800/50 rounded-xl p-10 border border-gray-700 backdrop-blur-md shadow-xl">
                <h2 className="text-3xl font-semibold text-white mb-8">训练历史</h2>
                <div className="overflow-x-auto -mx-2 px-2">
                    <table className="w-full text-base" style={{ minWidth: '900px' }}>
                        <thead>
                            <tr className="border-b-2 border-gray-600">
                                <th className="pb-8 px-8 text-left text-gray-400 font-semibold uppercase text-sm tracking-wider">状态</th>
                                <th className="pb-8 px-8 text-left text-gray-400 font-semibold uppercase text-sm tracking-wider">日期</th>
                                <th className="pb-8 px-8 text-left text-gray-400 font-semibold uppercase text-sm tracking-wider">数据范围</th>
                                <th className="pb-8 px-8 text-left text-gray-400 font-semibold uppercase text-sm tracking-wider">记录数</th>
                                <th className="pb-8 px-8 text-left text-gray-400 font-semibold uppercase text-sm tracking-wider">时长</th>
                                <th className="pb-8 px-8 text-left text-gray-400 font-semibold uppercase text-sm tracking-wider">MAE</th>
                                <th className="pb-8 px-8 text-left text-gray-400 font-semibold uppercase text-sm tracking-wider">RMSE</th>
                            </tr>
                        </thead>
                        <tbody>
                            {history.length === 0 ? (
                                <tr>
                                    <td colSpan={7} className="pt-8 pb-4 text-center text-gray-500">暂无训练历史</td>
                                </tr>
                            ) : (
                                history.map((run, index) => (
                                    <tr
                                        key={run.id}
                                        className={`border-b border-gray-700/30 hover:bg-gray-700/20 transition-colors ${index === 0 ? 'bg-blue-500/5' : ''
                                            }`}
                                    >
                                        {/* Status - Icon Only */}
                                        <td className="py-6 px-8">
                                            {run.success ? (
                                                <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20" style={{ color: '#4ade80' }}>
                                                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                                                </svg>
                                            ) : (
                                                <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20" style={{ color: '#f87171' }}>
                                                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                                                </svg>
                                            )}
                                        </td>

                                        {/* Date */}
                                        <td className="py-6 px-8 font-mono text-white whitespace-nowrap">
                                            {new Date(run.timestamp).toLocaleDateString('zh-CN', {
                                                year: 'numeric',
                                                month: '2-digit',
                                                day: '2-digit'
                                            }).replace(/\//g, '/')}
                                        </td>

                                        {/* Date Range */}
                                        <td className="py-6 px-8 text-gray-400 text-sm whitespace-nowrap">
                                            {run.data_info.date_range.replace(/to|至/g, '→')}
                                        </td>

                                        {/* Records */}
                                        <td className="py-6 px-8 text-gray-300 font-mono tabular-nums">
                                            {run.data_info.sensor_records.toLocaleString('zh-CN')}
                                        </td>

                                        {/* Duration */}
                                        <td className="py-6 px-8 text-gray-300 whitespace-nowrap">
                                            {run.duration_formatted}
                                        </td>

                                        {/* MAE */}
                                        <td className="py-6 px-8">
                                            <span className="inline-block px-4 py-2 rounded-md bg-blue-500/10 text-blue-300 font-mono text-base tabular-nums">
                                                {run.metrics.mae.toFixed(4)}
                                            </span>
                                        </td>

                                        {/* RMSE */}
                                        <td className="py-6 px-8">
                                            <span className="inline-block px-4 py-2 rounded-md bg-teal-500/10 text-teal-300 font-mono text-base tabular-nums">
                                                {run.metrics.rmse.toFixed(4)}
                                            </span>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default TrainingMonitor;
