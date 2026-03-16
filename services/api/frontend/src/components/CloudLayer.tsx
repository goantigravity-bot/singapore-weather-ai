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
    const [bounds, setBounds] = useState<[[number, number], [number, number]] | null>(null);
    const [currentIdx, setCurrentIdx] = useState(0);
    const [isPlaying, setIsPlaying] = useState(true);
    const [isLoading, setIsLoading] = useState(true);

    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const framesRef = useRef<SatelliteFrame[]>([]);
    const currentImageRef = useRef<HTMLImageElement | null>(null);
    const boundsRef = useRef<[[number, number], [number, number]] | null>(null);

    framesRef.current = frames;
    boundsRef.current = bounds;

    // 获取帧数据
    const fetchFrames = useCallback(async () => {
        try {
            setIsLoading(true);
            const resp = await fetch(`${API_BASE_URL}/satellite/frames`);
            if (!resp.ok) return;
            const data: FramesResponse = await resp.json();
            if (data.frames.length > 0) {
                setFrames(prev => {
                    const same = prev.length === data.frames.length
                        && prev.length > 0
                        && prev[0].timestamp === data.frames[0].timestamp
                        && prev[prev.length - 1].timestamp === data.frames[data.frames.length - 1].timestamp;
                    return same ? prev : data.frames;
                });
                setBounds(prev => prev ? prev : data.bounds);
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

    // 将云图绘制到 canvas 上（基于当前地图视口投影）
    const drawCloud = useCallback(() => {
        const canvas = canvasRef.current;
        const img = currentImageRef.current;
        const b = boundsRef.current;
        if (!canvas || !img || !b) return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // 将地理 bounds 投影到像素坐标
        // bounds 格式: [[south, west], [north, east]]
        const nw = map.latLngToContainerPoint([b[1][0], b[0][1]]); // NW = [north, west]
        const se = map.latLngToContainerPoint([b[0][0], b[1][1]]); // SE = [south, east]
        const x = nw.x;
        const y = nw.y;
        const w = se.x - nw.x;
        const h = se.y - nw.y;

        if (w > 0 && h > 0) {
            ctx.drawImage(img, x, y, w, h);
        }
    }, [map]);

    // Canvas 初始化（同 WindLayer 模式：挂载到 map container，视口大小）
    useEffect(() => {
        const container = map.getContainer();

        const canvas = document.createElement('canvas');
        canvas.style.position = 'absolute';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.pointerEvents = 'none';
        canvas.style.zIndex = '400'; // tile 之上、wind(450) 之下
        container.appendChild(canvas);
        canvasRef.current = canvas;

        const resizeCanvas = () => {
            const size = map.getSize();
            canvas.width = size.x;
            canvas.height = size.y;
            drawCloud();
        };

        resizeCanvas();

        // 地图移动/缩放时重绘
        map.on('move zoom viewreset resize', resizeCanvas);
        map.on('zoomstart', () => { canvas.style.display = 'none'; });
        map.on('zoomend', () => { canvas.style.display = 'block'; resizeCanvas(); });

        return () => {
            map.off('move zoom viewreset resize', resizeCanvas);
            if (canvas.parentNode) {
                canvas.parentNode.removeChild(canvas);
            }
            canvasRef.current = null;
        };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [map]);

    // 帧动画逻辑
    useEffect(() => {
        if (!isPlaying || frames.length <= 1) return;

        const scheduleNext = () => {
            const isLastFrame = currentIdx === frames.length - 1;
            const delay = isLastFrame ? LAST_FRAME_PAUSE_MS : FRAME_INTERVAL_MS;

            timerRef.current = setTimeout(() => {
                setCurrentIdx(prev => (prev + 1) % framesRef.current.length);
            }, delay);
        };

        scheduleNext();

        return () => {
            if (timerRef.current) clearTimeout(timerRef.current);
        };
    }, [isPlaying, currentIdx, frames.length]);

    // 更新当前帧图片
    useEffect(() => {
        if (!frames[currentIdx]) return;
        const img = new Image();
        img.onload = () => {
            currentImageRef.current = img;
            drawCloud();
        };
        img.src = frames[currentIdx].image;
    }, [currentIdx, frames, drawCloud]);

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
    const progress = frames.length > 1 ? (currentIdx / (frames.length - 1)) * 100 : 100;

    // 点击进度条跳转到对应帧
    const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        const idx = Math.round(pct * (frames.length - 1));
        setCurrentIdx(idx);
    };

    // 生成整点时刻标记
    const hourMarks: { pct: number; label: string }[] = [];
    if (frames.length > 1) {
        const seen = new Set<number>();
        frames.forEach((f, i) => {
            const d = new Date(f.timestamp);
            const h = d.getHours();
            if (d.getMinutes() === 0 && !seen.has(h)) {
                seen.add(h);
                hourMarks.push({
                    pct: (i / (frames.length - 1)) * 100,
                    label: `${h}`,
                });
            }
        });
    }

    // 用 Leaflet API 阻止点击穿透到地图
    const playerRef = useRef<HTMLDivElement | null>(null);
    useEffect(() => {
        if (playerRef.current) {
            L.DomEvent.disableClickPropagation(playerRef.current);
            L.DomEvent.disableScrollPropagation(playerRef.current);
        }
    });

    return (
        <div
            ref={playerRef}
            style={{
            position: 'absolute', bottom: '10px', right: '10px',
            zIndex: 1100,
            background: 'rgba(0,0,0,0.8)', backdropFilter: 'blur(10px)',
            borderRadius: '12px', padding: '10px 14px',
            display: 'flex', flexDirection: 'column', gap: '6px',
            width: '420px', pointerEvents: 'auto',
            boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
            border: '1px solid rgba(255,255,255,0.08)',
        }}>
            {/* 顶部行：播放按钮 + 标题 + 时间 + 帧计数 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <button
                    onClick={() => setIsPlaying(prev => !prev)}
                    style={{
                        background: 'none', border: 'none', color: '#fff',
                        cursor: 'pointer', fontSize: '18px', padding: '2px 4px',
                        flexShrink: 0,
                    }}
                    title={isPlaying ? 'Pause' : 'Play'}
                >
                    {isPlaying ? '⏸' : '▶️'}
                </button>
                <span style={{ color: '#999', fontSize: '11px', flexShrink: 0 }}>🛰️ IR Cloud</span>
                <span style={{
                    color: '#fff', fontSize: '15px', fontWeight: 700,
                    fontFamily: 'monospace', flexShrink: 0, marginLeft: 'auto',
                }}>
                    {new Date(currentFrame.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
            </div>

            {/* 可点击进度条 + 整点标记 */}
            <div
                onClick={handleProgressClick}
                style={{
                    width: '100%', height: '24px', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', position: 'relative',
                }}
            >
                {/* 进度条轨道 */}
                <div style={{
                    width: '100%', height: '4px', borderRadius: '2px',
                    background: 'rgba(255,255,255,0.15)', position: 'relative',
                }}>
                    {/* 进度填充 */}
                    <div style={{
                        width: `${progress}%`, height: '100%', borderRadius: '2px',
                        background: 'var(--accent-cyan, #00bcd4)',
                        transition: 'width 0.15s ease',
                    }} />
                    {/* 播放头 */}
                    <div style={{
                        position: 'absolute', top: '-4px',
                        left: `${progress}%`, transform: 'translateX(-50%)',
                        width: '10px', height: '10px', borderRadius: '50%',
                        background: 'var(--accent-cyan, #00bcd4)',
                        border: '2px solid #fff',
                        boxShadow: '0 0 4px rgba(0,0,0,0.5)',
                    }} />
                </div>
            </div>

            {/* 整点刻度标签 */}
            <div style={{ width: '100%', position: 'relative', height: '14px' }}>
                {hourMarks.map((m) => (
                    <span key={m.label} style={{
                        position: 'absolute', left: `${m.pct}%`, transform: 'translateX(-50%)',
                        fontSize: '9px', color: '#666', fontFamily: 'monospace',
                    }}>
                        {m.label}:00
                    </span>
                ))}
            </div>
        </div>
    );
};

export default CloudLayer;
