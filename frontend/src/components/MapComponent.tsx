import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents } from 'react-leaflet';
import axios from 'axios';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { API_BASE_URL } from '../config';

// Fix leafet marker icons
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

let DefaultIcon = L.icon({
    iconUrl: icon,
    shadowUrl: iconShadow,
    iconSize: [25, 41],
    iconAnchor: [12, 41]
});

L.Marker.prototype.options.icon = DefaultIcon;

interface Station {
    id: string;
    name: string;
    location: {
        latitude: number;
        longitude: number;
    }
}

interface Props {
    onStationClick: (lat: number, lon: number) => void;
    flyToCoords: { lat: number, lon: number } | null;
}

// Component to handle map movements and resizing
const MapController: React.FC<{ coords: { lat: number, lon: number } | null }> = ({ coords }) => {
    const map = useMap();

    useEffect(() => {
        // Force resize recalculation after mount
        setTimeout(() => {
            map.invalidateSize();
        }, 100);
    }, [map]);

    useEffect(() => {
        if (coords) {
            map.flyTo([coords.lat, coords.lon], 14, { duration: 2 });
        }
    }, [coords, map]);
    return null;
}

const LocationMarker: React.FC<{ onClick: (lat: number, lon: number) => void }> = ({ onClick }) => {
    useMapEvents({
        click(e) {
            onClick(e.latlng.lat, e.latlng.lng);
        },
    });
    return null;
}

const MapComponent: React.FC<Props & { highlightedStationId?: string }> = ({ onStationClick, flyToCoords, highlightedStationId }) => {
    const [stations, setStations] = useState<Station[]>([]);

    useEffect(() => {
        // Fetch stations on load
        axios.get(`${API_BASE_URL}/stations`)
            .then(res => setStations(res.data))
            .catch(err => console.error("Failed to fetch stations", err));
    }, []);

    const HighlightedIcon = L.icon({
        iconUrl: 'https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png',
        shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
        iconSize: [25, 41],
        iconAnchor: [12, 41],
        popupAnchor: [1, -34],
        shadowSize: [41, 41]
    });

    return (
        <MapContainer center={[1.3521, 103.8198]} zoom={11} scrollWheelZoom={true} zoomControl={false}>
            <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            <MapController coords={flyToCoords} />
            <LocationMarker onClick={onStationClick} />

            {stations.map(station => (
                <Marker
                    key={station.id}
                    position={[station.location.latitude, station.location.longitude]}
                    icon={station.id === highlightedStationId ? HighlightedIcon : DefaultIcon}
                    zIndexOffset={station.id === highlightedStationId ? 1000 : 0}
                    eventHandlers={{
                        click: () => {
                            onStationClick(station.location.latitude, station.location.longitude);
                        },
                    }}
                >
                    <Popup>
                        <strong>{station.name}</strong><br />ID: {station.id}
                    </Popup>
                </Marker>
            ))}
        </MapContainer>
    );
};

export default MapComponent;
