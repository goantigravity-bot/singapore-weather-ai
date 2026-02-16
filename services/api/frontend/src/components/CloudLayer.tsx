import { useEffect, useRef, useState, useCallback } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { API_BASE_URL } from '../config';

// ── 类型定义 ──

interface SatelliteFrame {
    image: string;   // data:image/png;base64,...
    time: string;    // "HH:MM"
    timestamp: string;
}

interface FramesResponse {
    frames: SatelliteFrame[];
    bounds: [[number, number], [number, number]];
}

// ── 常量 ──

const FRAME_INTERVAL_MS = 500;    // 普通帧间隔
const LAST_FRAME_PAUSE_MS = 2000; // 最新帧停留时间
const REFRESH_INTERVAL_MS = 5 * 60 * 1000; // 每 5 分钟刷新数据

const CloudLayer: React.FC = () => {
    const map = useMap();
    const [frames, setFrames] = useState<SatelliteFrame[]>([]);
    const [bounds, setBounds] = useState<L.LatLngBoundsExpression | null>(null);
    const [currentIdx, setCurrentIdx] = useState(0);
    const [isPlaying, setIsPlaying] = useState(true);
    const [isLoading, setIsLoading] = useState(true);

    const overlayRef = useRef<L.ImageOverlay | null>(null);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // 获取帧数据
    const fetchFrames = useCallback(async () => {
        try {
            setIsLoading(true);
            const resp = await fetch(`${API_BASE_URL}/satellite/frames`);
            if (!resp.ok) return;
            const data: FramesResponse = await resp.json();
            if (data.frames.length > 0) {
                setFrames(data.frames);
                setBounds(data.bounds as L.LatLngBoundsExpression);
                setCurrentIdx(0);
            }
        } catch (err) {
            console.error('Failed to fetch satellite frames:', err);
        } finally {
            setIsLoading(false);
        }
    }, []);

    // 初始加载 + 定时刷新
    useEffect(() => {
        fetchFrames();
        const interval = setInterval(fetchFrames, REFRESH_INTERVAL_MS);
        return () => clearInterval(interval);
    }, [fetchFrames]);

    // 管理 ImageOverlay 生命周期
    useEffect(() => {
        if (!bounds || frames.length === 0) return;

        // 创建或更新 overlay
        if (!overlayRef.current) {
            overlayRef.current = L.imageOverlay(
                frames[0].image,
                bounds as L.LatLngBoundsExpression,
                { opacity: 0.7, interactive: false, zIndex: 200 }
            ).addTo(map);
        }

        return () => {
            if (overlayRef.current) {
                map.removeLayer(overlayRef.current);
                overlayRef.current = null;
            }
        };
    }, [map, bounds, frames]);

    // 帧动画逻辑
    useEffect(() => {
        if (!isPlaying || frames.length <= 1 || !overlayRef.current) return;

        const scheduleNext = () => {
            // 最后一帧停留更久
            const isLastFrame = currentIdx === frames.length - 1;
            const delay = isLastFrame ? LAST_FRAME_PAUSE_MS : FRAME_INTERVAL_MS;

            timerRef.current = setTimeout(() => {
                setCurrentIdx(prev => (prev + 1) % frames.length);
            }, delay);
        };

        scheduleNext();

        return () => {
            if (timerRef.current) clearTimeout(timerRef.current);
        };
    }, [isPlaying, currentIdx, frames]);

    // 更新 overlay 图片
    useEffect(() => {
        if (overlayRef.current && frames[currentIdx]) {
            overlayRef.current.setUrl(frames[currentIdx].image);
        }
    }, [currentIdx, frames]);

    // 无帧数据时不渲染控件
    if (frames.length === 0) {
        if (isLoading) {
            return (
                <div style={{
                    position: 'absolute', bottom: '30px', right: '10px', zIndex: 1000,
                    background: 'rgba(0,0,0,0.7)', color: '#aaa',
                    borderRadius: '8px', padding: '8px 12px', fontSize: '12px',
                }}>
                    🛰️ Loading...
                </div>
            );
        }
        return null;
    }

    const currentFrame = frames[currentIdx];
    // 进度条百分比
    const progress = frames.length > 1 ? (currentIdx / (frames.length - 1)) * 100 : 100;

    return (
        <div style={{
            position: 'absolute', bottom: '30px', right: '10px', zIndex: 1000,
            background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)',
            borderRadius: '10px', padding: '8px 12px',
            display: 'flex', flexDirection: 'column', gap: '4px',
            minWidth: '160px', pointerEvents: 'auto',
        }}>
            {/* 标题行 */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                <span style={{ color: '#ccc', fontSize: '11px', fontWeight: 500 }}>
                    🛰️ IR Cloud
                </span>
                <span style={{ color: '#fff', fontSize: '13px', fontWeight: 700, fontFamily: 'monospace' }}>
                    {new Date(currentFrame.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
            </div>

            {/* 进度条 */}
            <div style={{
                width: '100%', height: '3px', borderRadius: '2px',
                background: 'rgba(255,255,255,0.15)',
            }}>
                <div style={{
                    width: `${progress}%`, height: '100%', borderRadius: '2px',
                    background: 'var(--accent-cyan, #00bcd4)',
                    transition: 'width 0.3s ease',
                }} />
            </div>

            {/* 控制行 */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <button
                    onClick={() => setIsPlaying(prev => !prev)}
                    style={{
                        background: 'none', border: 'none', color: '#fff',
                        cursor: 'pointer', fontSize: '14px', padding: '0 4px',
                    }}
                    title={isPlaying ? 'Pause' : 'Play'}
                >
                    {isPlaying ? '⏸' : '▶️'}
                </button>
                <span style={{ color: '#888', fontSize: '10px' }}>
                    {currentIdx + 1}/{frames.length}
                </span>
            </div>
        </div>
    );
};

export default CloudLayer;
