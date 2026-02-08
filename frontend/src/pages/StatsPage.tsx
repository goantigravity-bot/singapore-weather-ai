import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { API_BASE_URL } from '../config';
import { LABELS } from '../i18n/labels';

interface PopularLocation {
    name: string;
    count: number;
}

const StatsPage: React.FC = () => {
    const navigate = useNavigate();
    const [locations, setLocations] = useState<PopularLocation[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        axios.get(`${API_BASE_URL}/popular-searches`)
            .then(res => {
                setLocations(res.data);
                setLoading(false);
            })
            .catch(err => {
                console.error("Failed to fetch stats", err);
                setLoading(false);
            });
    }, []);

    const handleLocationClick = (locName: string) => {
        // Navigate back to map with search query
        navigate(`/?search=${encodeURIComponent(locName)}`);
    };

    return (
        <div className="dashboard-overlay" style={{
            height: 'auto',
            minHeight: '400px',
            maxHeight: '80vh',
            width: '340px',
            overflowY: 'auto'
        }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <h2 style={{ margin: 0, fontSize: '1.5rem' }}>{LABELS.stats.title} 📊</h2>
                <Link to="/" className="quick-link-chip" style={{ padding: '8px 12px' }}>
                    {LABELS.common.close} ❌
                </Link>
            </div>

            {loading ? (
                <div style={{ textAlign: 'center', padding: '20px', color: '#888' }}>
                    {LABELS.stats.loading}
                </div>
            ) : locations.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '20px', color: '#888' }}>
                    {LABELS.stats.noHistory}
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                    {locations.map((loc, index) => (
                        <div
                            key={loc.name}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                background: 'rgba(255,255,255,0.05)',
                                padding: '12px',
                                borderRadius: '12px',
                                border: '1px solid rgba(255,255,255,0.1)'
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                <div style={{
                                    width: '24px',
                                    height: '24px',
                                    background: index < 3 ? 'var(--accent-cyan)' : '#444',
                                    color: index < 3 ? '#000' : '#fff',
                                    borderRadius: '50%',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    fontWeight: 'bold',
                                    fontSize: '0.8rem'
                                }}>
                                    {index + 1}
                                </div>
                                <div>
                                    <div style={{ fontWeight: 'bold' }}>{loc.name}</div>
                                    <div style={{ fontSize: '0.8rem', color: '#aaa' }}>{loc.count} {LABELS.stats.searches}</div>
                                </div>
                            </div>

                            <button
                                onClick={() => handleLocationClick(loc.name)}
                                className="quick-link-chip"
                                style={{ padding: '6px 12px', fontSize: '0.8rem' }}
                            >
                                🗺️ {LABELS.stats.view}
                            </button>
                        </div>
                    ))}
                </div>
            )}

            <div style={{ marginTop: '20px', fontSize: '0.8rem', color: '#666', textAlign: 'center' }}>
                {LABELS.stats.footer}
            </div>
        </div>
    );
};

export default StatsPage;
