import { useState, useEffect } from 'react';
import axios from 'axios';
import MapComponent from './components/MapComponent';
import ForecastPanel from './components/ForecastPanel';
import './App.css';
import { API_BASE_URL } from './config';

interface ForecastResult {
  timestamp: string;
  location_query: string;
  nearest_station: {
    id: string;
    name: string;
  };
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [flyTo, setFlyTo] = useState<{ lat: number, lon: number } | null>(null);

  useEffect(() => {
    // Default location (Singapore Center - MacRitchie)
    const defaultLat = 1.3521;
    const defaultLon = 103.8198;

    const useDefaultLocation = () => {
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
          useDefaultLocation();
        },
        {
          enableHighAccuracy: false,
          timeout: 5000,
          maximumAge: 60000
        }
      );
    } else {
      useDefaultLocation();
    }
  }, []);

  const fetchForecast = async (params: any) => {
    setLoading(true);
    setError(null);
    try {
      const res = await axios.get(`${API_BASE_URL}/predict`, { params });
      setForecast(res.data);

      const stationsRes = await axios.get(`${API_BASE_URL}/stations`);
      const station = stationsRes.data.find((s: any) => s.id === res.data.nearest_station.id);
      if (station) {
        setFlyTo({ lat: station.location.latitude, lon: station.location.longitude });
      }

    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || "Failed to fetch forecast");
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    fetchForecast({ location: searchQuery });
  };

  const handleMapClick = (lat: number, lon: number) => {
    fetchForecast({ lat, lon });
  };

  return (
    <div id="app-root">
      {/* Search Bar */}
      <form className="search-bar" onSubmit={handleSearch}>
        <input
          type="text"
          className="search-input"
          placeholder="Enter location (e.g. Sentosa)..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </form>

      {/* Forecast Overlay */}
      <ForecastPanel data={forecast} loading={loading} error={error} />

      {/* Map */}
      <MapComponent
        onStationClick={handleMapClick}
        flyToCoords={flyTo}
        highlightedStationId={forecast?.nearest_station.id}
      />
    </div>
  );
}

export default App;
