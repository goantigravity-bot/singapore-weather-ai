import { useState, useEffect } from 'react';
import axios from 'axios';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import MapComponent from './components/MapComponent';
import ForecastPanel from './components/ForecastPanel';
import QuickLinks from './components/QuickLinks';
import SettingsPage from './pages/SettingsPage';
import StatsPage from './pages/StatsPage';
import AboutPage from './pages/AboutPage';
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
  };
}

function App() {
  const [searchQuery, setSearchQuery] = useState('');
  const [forecast, setForecast] = useState<ForecastResult | null>(null);
  const [pathForecast, setPathForecast] = useState<any>(null); // New State for Path
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flyTo, setFlyTo] = useState<{ lat: number, lon: number } | null>(null);
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  useEffect(() => {
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
  }, []);

  const fetchForecast = async (params: any) => {
    setLoading(true);
    setError(null);
    setPathForecast(null); // Reset path

    try {

      // 1. If searching by string, try Path Prediction FIRST
      if (params.location && !params.lat) {
        try {
          console.log("Attempting Path Forecast for:", params.location);
          const pathRes = await axios.get(`${API_BASE_URL}/predict/path`, { params: { query: params.location } });

          if (pathRes.data && pathRes.data.points && pathRes.data.points.length > 0) {
            // Success! It's a path.
            const points = pathRes.data.points;

            // Construct path data for Map
            setPathForecast({
              path: points.map((p: any) => [p.lat, p.lon]),
              points: points
            });

            // Focus Map on first point
            setFlyTo({ lat: points[0].lat, lon: points[0].lon });

            // Set 'forecast' to a summary or just the first point to show something in standard panel
            const first = points[0];
            setForecast({
              timestamp: new Date().toISOString(),
              location_query: params.location,
              nearest_station: { id: 'path', name: `${params.location} (Path)` },
              forecast: {
                rainfall_mm_next_10min: first.forecast.rainfall, // Just show first point data as summary
                description: "Path Forecast (See Map)"
              },
              current_weather: {
                temperature: first.forecast.temperature,
                humidity: null
              }
            });
            return; // Stop here, don't do single point forecast
          }
        } catch (e) {
          console.log("Path forecast failed or not a path, falling back to single point.", e);
          // Ignore error, fallback to normal
        }
      }

      // 2. Normal Single Point Forecast (Fallback or Lat/Lon)
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
    <ConfigProvider>
      <BrowserRouter>
        <div id="app-root">
          {/* Always Visible Components */}
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

          <SideMenu isOpen={isMenuOpen} onClose={() => setIsMenuOpen(false)} />


          <QuickLinks onSelectLocation={handleQuickLink} />

          <MapComponent
            onStationClick={handleMapClick}
            flyToCoords={flyTo}
            contributingStationIds={forecast?.contributing_stations}
            pathData={pathForecast}
          />

          {/* Overlay Router */}
          <Routes>
            <Route path="/" element={
              <ForecastPanel data={forecast} loading={loading} error={error} />
            } />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/stats" element={<StatsPage />} />
            <Route path="/about" element={<AboutPage />} />
          </Routes>
        </div>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
