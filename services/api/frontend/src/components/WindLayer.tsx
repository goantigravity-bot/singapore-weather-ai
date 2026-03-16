import { useEffect, useRef, useCallback, useState } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';

// ── 类型定义 ──

interface WindStation {
    id: string;
    name: string;
    lat: number;
    lon: number;
}

interface WindReading {
    stationId: string;
    speed: number;    // knots
    direction: number; // degrees, 气象学惯例：风来的方向
}

interface VectorField {
    grid: Float32Array; // 交错存储 [u0,v0, u1,v1, ...], 行优先
    nx: number;
    ny: number;
    bounds: { latMin: number; latMax: number; lonMin: number; lonMax: number };
}

interface Particle {
    x: number;    // 经度
    y: number;    // 纬度
    age: number;
    maxAge: number;
}

// ── 常量 ──

// 新加坡的地理范围
const SG_BOUNDS = {
    latMin: 1.15,
    latMax: 1.47,
    lonMin: 103.58,
    lonMax: 104.1,
};

const GRID_RES = 0.005;  // 网格分辨率（约 500m）
const NX = Math.ceil((SG_BOUNDS.lonMax - SG_BOUNDS.lonMin) / GRID_RES);
const NY = Math.ceil((SG_BOUNDS.latMax - SG_BOUNDS.latMin) / GRID_RES);

const PARTICLE_COUNT = 2500;
const PARTICLE_MIN_AGE = 60;
const PARTICLE_MAX_AGE = 150;
const IDW_POWER = 2;

// 风速→颜色映射
const WIND_COLORS = [
    { threshold: 0, color: [76, 175, 80] },   // 微风 - 绿
    { threshold: 2, color: [33, 150, 243] },   // 轻风 - 蓝
    { threshold: 5, color: [255, 152, 0] },    // 和风 - 橙
    { threshold: 8, color: [244, 67, 54] },    // 强风 - 红
];

// ── 工具函数 ──

/** 气象风向 → u/v 分量（风去的方向） */
const windToUV = (speed: number, dirDeg: number): [number, number] => {
    const rad = (dirDeg * Math.PI) / 180;
    // 气象学惯例：direction 是风来的方向
    // u = -speed * sin(dir), v = -speed * cos(dir)
    return [-speed * Math.sin(rad), -speed * Math.cos(rad)];
};

/** 风速映射颜色 */
const speedToColor = (speed: number): [number, number, number] => {
    for (let i = WIND_COLORS.length - 1; i >= 0; i--) {
        if (speed >= WIND_COLORS[i].threshold) {
            return WIND_COLORS[i].color as [number, number, number];
        }
    }
    return WIND_COLORS[0].color as [number, number, number];
};

/** IDW 插值：从离散站点生成连续向量场网格 */
const buildVectorField = (
    stations: WindStation[],
    readings: Map<string, WindReading>,
): VectorField | null => {
    // 过滤有效数据的站点
    const validStations = stations.filter(s => readings.has(s.id));
    if (validStations.length < 2) return null;

    const grid = new Float32Array(NX * NY * 2);

    for (let iy = 0; iy < NY; iy++) {
        const lat = SG_BOUNDS.latMax - iy * GRID_RES; // 从北到南
        for (let ix = 0; ix < NX; ix++) {
            const lon = SG_BOUNDS.lonMin + ix * GRID_RES;

            let wSum = 0;
            let uSum = 0;
            let vSum = 0;

            for (const station of validStations) {
                const reading = readings.get(station.id)!;
                const dx = lon - station.lon;
                const dy = lat - station.lat;
                const dist = Math.sqrt(dx * dx + dy * dy);

                // 避免除零：如果恰好在站点上，直接用站点值
                if (dist < 1e-6) {
                    const [u, v] = windToUV(reading.speed, reading.direction);
                    uSum = u;
                    vSum = v;
                    wSum = 1;
                    break;
                }

                const w = 1 / Math.pow(dist, IDW_POWER);
                const [u, v] = windToUV(reading.speed, reading.direction);
                uSum += w * u;
                vSum += w * v;
                wSum += w;
            }

            const idx = (iy * NX + ix) * 2;
            grid[idx] = uSum / wSum;
            grid[idx + 1] = vSum / wSum;
        }
    }

    return { grid, nx: NX, ny: NY, bounds: SG_BOUNDS };
};

/** 在向量场中双线性插值查询某点的 u/v */
const sampleField = (field: VectorField, lon: number, lat: number): [number, number] | null => {
    const { bounds, nx, ny, grid } = field;

    // 归一化到网格坐标
    const fx = ((lon - bounds.lonMin) / (bounds.lonMax - bounds.lonMin)) * (nx - 1);
    const fy = ((bounds.latMax - lat) / (bounds.latMax - bounds.latMin)) * (ny - 1);

    if (fx < 0 || fx >= nx - 1 || fy < 0 || fy >= ny - 1) return null;

    const ix = Math.floor(fx);
    const iy = Math.floor(fy);
    const dx = fx - ix;
    const dy = fy - iy;

    // 双线性插值 4 个角点
    const i00 = (iy * nx + ix) * 2;
    const i10 = (iy * nx + ix + 1) * 2;
    const i01 = ((iy + 1) * nx + ix) * 2;
    const i11 = ((iy + 1) * nx + ix + 1) * 2;

    const u = (1 - dx) * (1 - dy) * grid[i00]
        + dx * (1 - dy) * grid[i10]
        + (1 - dx) * dy * grid[i01]
        + dx * dy * grid[i11];

    const v = (1 - dx) * (1 - dy) * grid[i00 + 1]
        + dx * (1 - dy) * grid[i10 + 1]
        + (1 - dx) * dy * grid[i01 + 1]
        + dx * dy * grid[i11 + 1];

    return [u, v];
};

// ── 组件 ──

const WindLayer: React.FC = () => {
    const map = useMap();
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const animFrameRef = useRef<number>(0);
    const particlesRef = useRef<Particle[]>([]);
    const fieldRef = useRef<VectorField | null>(null);
    const [stations, setStations] = useState<WindStation[]>([]);
    const [readings, setReadings] = useState<Map<string, WindReading>>(new Map());

    // ── 数据获取 ──
    const fetchWindData = useCallback(async () => {
        try {
            const [speedRes, dirRes] = await Promise.all([
                fetch('https://api-open.data.gov.sg/v2/real-time/api/wind-speed'),
                fetch('https://api-open.data.gov.sg/v2/real-time/api/wind-direction'),
            ]);

            const speedData = await speedRes.json();
            const dirData = await dirRes.json();

            if (speedData.code !== 0 || dirData.code !== 0) return;

            const stationList: WindStation[] = speedData.data.stations.map((s: any) => ({
                id: s.id,
                name: s.name,
                lat: s.location.latitude,
                lon: s.location.longitude,
            }));
            setStations(stationList);

            const speedReadings = speedData.data.readings;
            const dirReadings = dirData.data.readings;
            if (!speedReadings?.length || !dirReadings?.length) return;

            const latestSpeed = speedReadings[speedReadings.length - 1];
            const latestDir = dirReadings[dirReadings.length - 1];

            const readingMap = new Map<string, WindReading>();
            const speedMap = new Map<string, number>();
            latestSpeed.data?.forEach((item: any) => {
                speedMap.set(item.stationId, item.value);
            });
            latestDir.data?.forEach((item: any) => {
                const speed = speedMap.get(item.stationId);
                if (speed !== undefined) {
                    readingMap.set(item.stationId, {
                        stationId: item.stationId,
                        speed,
                        direction: item.value,
                    });
                }
            });

            setReadings(readingMap);
        } catch (err) {
            console.error('Failed to fetch wind data:', err);
        }
    }, []);

    // 首次加载 + 定时刷新
    useEffect(() => {
        fetchWindData();
        const interval = setInterval(fetchWindData, 5 * 60 * 1000);
        return () => clearInterval(interval);
    }, [fetchWindData]);

    // ── 数据变更时重建向量场 ──
    useEffect(() => {
        if (stations.length > 0 && readings.size > 0) {
            fieldRef.current = buildVectorField(stations, readings);
        }
    }, [stations, readings]);

    // ── Canvas 初始化与动画循环 ──
    useEffect(() => {
        const container = map.getContainer();

        // 创建 Canvas 叠加层
        const canvas = document.createElement('canvas');
        canvas.style.position = 'absolute';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.pointerEvents = 'none';
        canvas.style.zIndex = '450'; // 在 tile 层之上、marker 之下
        container.appendChild(canvas);
        canvasRef.current = canvas;

        const resizeCanvas = () => {
            const size = map.getSize();
            canvas.width = size.x;
            canvas.height = size.y;
        };
        resizeCanvas();

        // 初始化粒子
        const initParticles = () => {
            const particles: Particle[] = [];
            for (let i = 0; i < PARTICLE_COUNT; i++) {
                particles.push(randomParticle());
            }
            particlesRef.current = particles;
        };

        const randomParticle = (): Particle => ({
            x: SG_BOUNDS.lonMin + Math.random() * (SG_BOUNDS.lonMax - SG_BOUNDS.lonMin),
            y: SG_BOUNDS.latMin + Math.random() * (SG_BOUNDS.latMax - SG_BOUNDS.latMin),
            age: 0,
            maxAge: PARTICLE_MIN_AGE + Math.random() * (PARTICLE_MAX_AGE - PARTICLE_MIN_AGE),
        });

        initParticles();

        // 动画循环
        const ctx = canvas.getContext('2d')!;

        const animate = () => {
            const field = fieldRef.current;
            if (!field) {
                animFrameRef.current = requestAnimationFrame(animate);
                return;
            }

            const w = canvas.width;
            const h = canvas.height;

            // 拖尾效果：用半透明覆盖而非完全清除
            ctx.fillStyle = 'rgba(0, 0, 0, 0.85)';
            ctx.globalCompositeOperation = 'destination-in';
            ctx.fillRect(0, 0, w, h);
            ctx.globalCompositeOperation = 'source-over';

            const zoom = map.getZoom();
            // 粒子速度比例：根据缩放级别调节运动幅度（降速让流动方向更清晰）
            const speedScale = 0.00003 * Math.pow(2, zoom - 11);

            const particles = particlesRef.current;

            for (let i = 0; i < particles.length; i++) {
                const p = particles[i];
                const uv = sampleField(field, p.x, p.y);

                if (!uv || p.age >= p.maxAge) {
                    // 粒子越界或到寿 → 重新投放
                    particles[i] = randomParticle();
                    continue;
                }

                const [u, v] = uv;
                const speed = Math.sqrt(u * u + v * v);

                // 旧位置 → 屏幕坐标
                const oldPt = map.latLngToContainerPoint(L.latLng(p.y, p.x));

                // 更新位置
                p.x += u * speedScale;
                p.y += v * speedScale;
                p.age++;

                // 新位置 → 屏幕坐标
                const newPt = map.latLngToContainerPoint(L.latLng(p.y, p.x));

                // 绘制粒子轨迹线
                const [r, g, b] = speedToColor(speed);
                // 粒子透明度随年龄渐变，中段最亮
                const lifeRatio = p.age / p.maxAge;
                const alpha = Math.sin(lifeRatio * Math.PI) * 0.8;

                ctx.beginPath();
                ctx.moveTo(oldPt.x, oldPt.y);
                ctx.lineTo(newPt.x, newPt.y);
                ctx.strokeStyle = `rgba(${r},${g},${b},${alpha})`;
                ctx.lineWidth = speed > 5 ? 2 : 1.2;
                ctx.stroke();
            }

            animFrameRef.current = requestAnimationFrame(animate);
        };

        animFrameRef.current = requestAnimationFrame(animate);

        // 地图事件：缩放/平移时调整 Canvas 并重置粒子
        const onMoveEnd = () => {
            resizeCanvas();
            // 清空画布避免残留
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        };

        const onZoomStart = () => {
            // 缩放开始时隐藏 canvas 避免错位
            canvas.style.display = 'none';
        };

        const onZoomEnd = () => {
            resizeCanvas();
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            canvas.style.display = 'block';
        };

        map.on('moveend', onMoveEnd);
        map.on('zoomstart', onZoomStart);
        map.on('zoomend', onZoomEnd);

        return () => {
            cancelAnimationFrame(animFrameRef.current);
            map.off('moveend', onMoveEnd);
            map.off('zoomstart', onZoomStart);
            map.off('zoomend', onZoomEnd);
            if (canvas.parentNode) {
                canvas.parentNode.removeChild(canvas);
            }
        };
    }, [map]);

    // 风速图例（m/s → km/h）
    const legend = WIND_COLORS.map((wc, i) => {
        const nextThreshold = WIND_COLORS[i + 1]?.threshold;
        const kmhMin = Math.round(wc.threshold * 3.6);
        const kmhMax = nextThreshold != null ? Math.round(nextThreshold * 3.6) : null;
        const label = kmhMax != null ? `${kmhMin}–${kmhMax}` : `>${kmhMin}`;
        return { color: wc.color, label };
    });

    return (
        <div style={{
            position: 'absolute', bottom: '10px', left: '10px', zIndex: 1100,
            background: 'rgba(0,0,0,0.75)', backdropFilter: 'blur(8px)',
            borderRadius: '10px', padding: '8px 12px',
            pointerEvents: 'auto', display: 'flex', flexDirection: 'column', gap: '4px',
        }}>
            <span style={{ color: '#999', fontSize: '10px', fontWeight: 600, letterSpacing: '0.5px' }}>
                WIND (km/h)
            </span>
            {legend.map((item) => (
                <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{
                        width: '20px', height: '3px', borderRadius: '1px',
                        background: `rgb(${item.color[0]},${item.color[1]},${item.color[2]})`,
                    }} />
                    <span style={{ color: '#ccc', fontSize: '11px', fontFamily: 'monospace' }}>
                        {item.label}
                    </span>
                </div>
            ))}
        </div>
    );
};

export default WindLayer;
