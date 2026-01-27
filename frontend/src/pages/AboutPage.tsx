import React from 'react';
import { Link } from 'react-router-dom';

const AboutPage: React.FC = () => {
    return (
        <div className="dashboard-overlay" style={{
            height: 'auto',
            width: '340px',
            textAlign: 'center'
        }}>
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '10px' }}>
                <Link to="/" className="quick-link-chip" style={{ padding: '8px 12px' }}>❌</Link>
            </div>

            <div style={{ padding: '20px 0' }}>
                <div style={{ fontSize: '3rem', marginBottom: '10px' }}>🌦️</div>
                <h2 style={{ margin: '0 0 10px 0', fontSize: '1.5rem', color: 'var(--accent-cyan)' }}>
                    Singapore Weather AI
                </h2>
                <div style={{
                    display: 'inline-block',
                    background: 'rgba(255, 165, 0, 0.2)',
                    border: '1px solid orange',
                    color: 'orange',
                    padding: '4px 12px',
                    borderRadius: '12px',
                    fontSize: '0.9rem',
                    fontWeight: 'bold',
                }}>
                    v0.5
                </div>

                <p style={{ color: '#aaa', lineHeight: '1.6', margin: '0 0 20px 0' }}>
                    A real-time weather forecasting tool powered by AI and satellite imagery.
                    Predicts rainfall 10-60 minutes ahead for precise locations across Singapore.
                </p>

                <div style={{ fontSize: '0.8rem', color: '#666' }}>
                    © 2026 Singapore Weather AI
                </div>
            </div>
        </div >
    );
};

export default AboutPage;
