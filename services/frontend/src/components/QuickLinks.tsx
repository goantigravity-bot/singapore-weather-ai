import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { API_BASE_URL } from '../config';

interface QuickLinksProps {
    onSelectLocation: (locationName: string) => void;
}

interface PopularLocation {
    name: string;
    count: number;
}

// Fallback locations in case DB is empty
const PRESET_LOCATIONS = [
    { name: "Sentosa", icon: "🎡" },
    { name: "Gardens by the Bay", icon: "🌳" },
    { name: "East Coast Park", icon: "🚴" },
    { name: "MacRitchie Reservoir", icon: "🐒" },
    { name: "Botanic Gardens", icon: "🌿" },
    { name: "Pulau Ubin", icon: "🏝️" },
];

const QuickLinks: React.FC<QuickLinksProps> = ({ onSelectLocation }) => {
    const [locations, setLocations] = useState<{ name: string, icon: string }[]>(PRESET_LOCATIONS);

    useEffect(() => {
        const fetchPopular = async () => {
            try {
                const res = await axios.get(`${API_BASE_URL}/popular-searches`);
                if (res.data && res.data.length > 0) {
                    // Map API data to format with icons (randomly assigned or default)
                    const popular = res.data.map((item: PopularLocation) => ({
                        name: item.name,
                        icon: "📍" // Default icon for dynamic searches
                    }));
                    setLocations(popular);
                }
            } catch (err) {
                console.error("Failed to fetch popular searches", err);
                // Keep presets on error
            }
        };

        fetchPopular();
    }, []);

    return (
        <>
            {/* Desktop: Chips */}
            <div className="quick-links-container desktop-only">
                {locations.map((loc) => (
                    <button
                        key={loc.name}
                        className="quick-link-chip"
                        onClick={() => onSelectLocation(loc.name)}
                    >
                        <span className="quick-link-icon">{loc.icon}</span>
                        {loc.name}
                    </button>
                ))}
            </div>


        </>
    );
};

export default QuickLinks;
