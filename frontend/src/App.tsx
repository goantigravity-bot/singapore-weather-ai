import { useState, useEffect } from 'react';
import axios from 'axios';
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom';
import MapComponent from './components/MapComponent';
import ForecastPanel from './components/ForecastPanel';
import QuickLinks from './components/QuickLinks';
import SettingsPage from './pages/SettingsPage';
import StatsPage from './pages/StatsPage';
import AboutPage from './pages/AboutPage';
import TrainingMonitor from './pages/TrainingMonitor';
import SideMenu from './components/SideMenu';
import { ConfigProvider } from './context/ConfigContext';
import './App.css';
import { API_BASE_URL } from './config';

interface ForecastResult {
  timestamp: string;
  location_query: string;
  nearest_station: {
    id: string;
    name: string;
  };
  contributing_stations?: string[];
  forecast: {
    rainfall_mm_next_10min: number;
    description: string;
  };
  current_weather: {
    temperature: number | null;
    humidity: number | null;
    pm25: number | null;
  };
}

function AppContent() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [forecast, setForecast] = useState<ForecastResult | null>(null);
  const [pathForecast, setPathForecast] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flyTo, setFlyTo] = useState<{ lat: number, lon: number } | null>(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  // 检查是否在训练监控页面
  const isTrainingPage = location.pathname === '/training';

  useEffect(() => {
    // 如果在训练页面,跳过默认位置加载
    if (isTrainingPage) return;

    // Default location (Singapore Center - MacRitchie)
    const defaultLat = 1.3521;
    const defaultLon = 103.8198;

    const fallbackToDefault = () => {
      console.log("Using default location fallback.");
      fetchForecast({ lat: defaultLat, lon: defaultLon });
    };

    // Try to get user location on load
    if ("geolocation" in navigator) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const { latitude, longitude } = position.coords;
          console.log("Got user location:", latitude, longitude);
          fetchForecast({ lat: latitude, lon: longitude });
          setFlyTo({ lat: latitude, lon: longitude });
        },
        (error) => {
          console.warn("Geolocation denied or failed:", error);
          fallbackToDefault();
        },
        {
          enableHighAccuracy: false,
          timeout: 5000,
          maximumAge: 60000
        }
      );
    } else {
      fallbackToDefault();
    }
  }, [isTrainingPage]);

  const fetchForecast = async (params: any) => {
    setLoading(true);
    setError(null);
    setPathForecast(null);

    try {

      // 1. If searching by string, try Path Prediction FIRST
      if (params.location && !params.lat) {
        try {
          console.log("Attempting Path Forecast for:", params.location);
          const pathRes = await axios.get(`${API_BASE_URL}/predict/path`, { params: { query: params.location } });

          if (pathRes.data && pathRes.data.points && pathRes.data.points.length > 0) {
            const points = pathRes.data.points;

            setPathForecast({
              path: points.map((p: any) => [p.lat, p.lon]),
              points: points
            });

            setFlyTo({ lat: points[0].lat, lon: points[0].lon });

            const first = points[0];
            setForecast({
              timestamp: new Date().toISOString(),
              location_query: params.location,
              nearest_station: { id: 'path', name: `${params.location} (Path)` },
              forecast: {
                rainfall_mm_next_10min: first.forecast.rainfall,
                description: "Path Forecast (See Map)"
              },
              current_weather: {
                temperature: first.forecast.temperature,
                humidity: null,
                pm25: null
              }
            });
            return;
          }
        } catch (e) {
          console.log("Path forecast failed or not a path, falling back to single point.", e);
        }
      }

      // 2. Normal Single Point Forecast
      const res = await axios.get(`${API_BASE_URL}/predict`, { params });
      setForecast(res.data);

      const stationsRes = await axios.get(`${API_BASE_URL}/stations`);
      if (params.lat && params.lon) {
        setFlyTo({ lat: params.lat, lon: params.lon });
      } else {
        const station = stationsRes.data.find((s: any) => s.id === res.data.nearest_station.id);
        if (station) {
          setFlyTo({ lat: station.location.latitude, lon: station.location.longitude });
        }
      }

    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || "Failed to fetch forecast");
    } finally {
      setLoading(false);
    }
  };

  const logSearch = async (query: string) => {
    try {
      await axios.post(`${API_BASE_URL}/log-search`, { query });
    } catch (err) {
      console.error("Failed to log search", err);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    fetchForecast({ location: searchQuery });
    logSearch(searchQuery);
  };

  const handleQuickLink = (location: string) => {
    setSearchQuery(location);
    fetchForecast({ location });
    logSearch(location);
  };

  const handleMapClick = (lat: number, lon: number) => {
    fetchForecast({ lat, lon });
  };

  return (
    <div id="app-root">
      {/* 侧边菜单始终可用 */}
      <SideMenu isOpen={isMenuOpen} onClose={() => setIsMenuOpen(false)} />

      {/* 只在非训练页面显示主页组件 */}
      {!isTrainingPage && (
        <>
          <div className="search-bar" style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '0 10px', background: 'transparent' }}>
            <button onClick={() => setIsMenuOpen(true)} className="burger-btn">
              ☰
            </button>
            <form onSubmit={handleSearch} style={{ flex: 1, position: 'relative' }}>
              <input
                type="text"
                className="search-input"
                placeholder="Enter location (e.g. Sentosa)..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ width: '100%' }}
              />
            </form>
          </div>

          <QuickLinks onSelectLocation={handleQuickLink} />

          <MapComponent
            onStationClick={handleMapClick}
            flyToCoords={flyTo}
            contributingStationIds={forecast?.contributing_stations}
            pathData={pathForecast}
          />
        </>
      )}

      {/* 训练页面显示导航栏 */}
      {isTrainingPage && (
        <div className="search-bar" style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
          padding: '0 10px',
          background: 'rgba(0, 0, 0, 0.7)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={() => navigate('/')}
              className="burger-btn"
              style={{ fontSize: '1.2rem' }}
              title="返回主页"
            >
              ←
            </button>
            <h2 style={{ color: 'white', margin: 0, fontSize: '1.2rem' }}>训练监控</h2>
          </div>
          <button onClick={() => setIsMenuOpen(true)} className="burger-btn">
            ☰
          </button>
        </div>
      )}

      {/* 路由内容 */}
      <Routes>
        <Route path="/" element={
          <ForecastPanel data={forecast} loading={loading} error={error} />
        } />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/stats" element={<StatsPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/training" element={<TrainingMonitor />} />
      </Routes>
    </div>
  );
}

function App() {
  return (
    <ConfigProvider>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
