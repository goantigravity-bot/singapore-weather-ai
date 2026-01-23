import React from 'react';

interface QuickLinksProps {
    onSelectLocation: (locationName: string) => void;
}

const LOCATIONS = [
    { name: "Sentosa", icon: "🎡" },
    { name: "Gardens by the Bay", icon: "🌳" },
    { name: "East Coast Park", icon: "🚴" },
    { name: "MacRitchie Reservoir", icon: "🐒" },
    { name: "Botanic Gardens", icon: "🌿" },
    { name: "Pulau Ubin", icon: "🏝️" },
];

const QuickLinks: React.FC<QuickLinksProps> = ({ onSelectLocation }) => {
    return (
        <>
            {/* Desktop: Chips */}
            <div className="quick-links-container desktop-only">
                {LOCATIONS.map((loc) => (
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

            {/* Mobile: Dropdown */}
            <div className="quick-links-mobile mobile-only">
                <select
                    className="quick-links-select"
                    onChange={(e) => {
                        if (e.target.value) onSelectLocation(e.target.value);
                    }}
                    defaultValue=""
                >
                    <option value="" disabled>✨ Select Popular Location</option>
                    {LOCATIONS.map((loc) => (
                        <option key={loc.name} value={loc.name}>
                            {loc.icon} {loc.name}
                        </option>
                    ))}
                </select>
            </div>
        </>
    );
};

export default QuickLinks;
