import React, { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents, Polygon, Polyline } from 'react-leaflet';
import axios from 'axios';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { API_BASE_URL } from '../config';
import { useConfig } from '../context/ConfigContext';

// ... (icons code) ...

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

// Custom Icons
const createIcon = (colorUrl: string) => L.icon({
    iconUrl: colorUrl,
    shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/0.7.7/images/marker-shadow.png',
    iconSize: [25, 41],
    iconAnchor: [12, 41],
    popupAnchor: [1, -34],
    shadowSize: [41, 41]
});

const BlueIcon = createIcon('https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-blue.png');
const GreenIcon = createIcon('https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-green.png');
const RedIcon = createIcon('https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-red.png');


const MapComponent: React.FC<Props & {
    contributingStationIds?: string[],
    pathData?: {
        path: [number, number][];
        points: {
            lat: number;
            lon: number;
            forecast: {
                rainfall: number;
                description: string;
                temperature: number | null;
            }
        }[];
    } | null
}> = ({ onStationClick, flyToCoords, contributingStationIds, pathData }) => {
    const [stations, setStations] = useState<Station[]>([]);
    const { showTriangle, showStations } = useConfig();

    useEffect(() => {
        // Fetch stations on load
        axios.get(`${API_BASE_URL}/stations`)
            .then(res => setStations(res.data))
            .catch(err => console.error("Failed to fetch stations", err));
    }, []);

    // Calculate Triangle Path
    const trianglePath: [number, number][] = [];
    if (showTriangle && contributingStationIds && stations.length > 0) {
        // Find coords for each contributing ID
        contributingStationIds.forEach(id => {
            const s = stations.find(st => st.id === id);
            if (s) {
                trianglePath.push([s.location.latitude, s.location.longitude]);
            }
        });
    }

    return (
        <MapContainer center={[1.3521, 103.8198]} zoom={11} scrollWheelZoom={true} zoomControl={false}>
            <TileLayer
                attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            />

            <MapController coords={flyToCoords} />
            <LocationMarker onClick={onStationClick} />

            {/* Draw Interpolation Triangle/Line */}
            {trianglePath.length >= 2 && (
                trianglePath.length === 2 ? (
                    <Polyline
                        positions={trianglePath}
                        pathOptions={{ color: 'orange', dashArray: '10, 10', opacity: 0.8, weight: 2 }}
                    />
                ) : (
                    <Polygon
                        positions={trianglePath}
                        pathOptions={{ color: 'orange', dashArray: '10, 10', fillColor: 'orange', fillOpacity: 0.1, weight: 2 }}
                    />
                )
            )}

            {/* Path Rendering */}
            {pathData && (
                <>
                    {/* The Path Line */}
                    <Polyline
                        positions={pathData.path}
                        pathOptions={{ color: 'purple', weight: 4, opacity: 0.7 }}
                    />

                    {/* Forecast Points along Path */}
                    {pathData.points.map((pt, idx) => (
                        <Marker
                            key={`path-pt-${idx}`}
                            position={[pt.lat, pt.lon]}
                            icon={RedIcon}
                            zIndexOffset={1500}
                        >
                            <Popup>
                                <strong>Path Point {idx + 1}</strong><br />
                                Rainfall: {pt.forecast.rainfall}mm<br />
                                {pt.forecast.description}<br />
                                {pt.forecast.temperature && `Temp: ${pt.forecast.temperature}°C`}
                            </Popup>
                        </Marker>
                    ))}
                </>
            )}

            {/* 1. Render User Selected Location (Red) */}
            {flyToCoords && (
                <Marker
                    position={[flyToCoords.lat, flyToCoords.lon]}
                    icon={RedIcon}
                    zIndexOffset={2000} // Highest priority
                >
                    <Popup>
                        <strong>Selected Location</strong>
                    </Popup>
                </Marker>
            )}

            {/* 2. Render Sensor Stations (Green or Blue) - only if showStations is enabled */}
            {showStations && stations.map(station => {
                const isContributing = contributingStationIds?.includes(station.id);
                // If this station happens to be exactly the user location (unlikely with float precision but possible),
                // we might want to hide it or let Red cover it.

                return (
                    <Marker
                        key={station.id}
                        position={[station.location.latitude, station.location.longitude]}
                        icon={isContributing ? GreenIcon : BlueIcon}
                        zIndexOffset={isContributing ? 1000 : 0} // Contributing on top of passive
                        eventHandlers={{
                            click: () => {
                                onStationClick(station.location.latitude, station.location.longitude);
                            },
                        }}
                    >
                        <Popup>
                            <strong>{station.name}</strong><br />
                            ID: {station.id}<br />
                            {isContributing && <span style={{ color: 'green', fontWeight: 'bold' }}>Running...</span>}
                        </Popup>
                    </Marker>
                );
            })}
        </MapContainer>
    );
};

export default MapComponent;
