import React from 'react';
import { Link } from 'react-router-dom';

interface SideMenuProps {
    isOpen: boolean;
    onClose: () => void;
}

const SideMenu: React.FC<SideMenuProps> = ({ isOpen, onClose }) => {
    return (
        <>
            {/* Backdrop */}
            <div
                className={`side-menu-backdrop ${isOpen ? 'open' : ''}`}
                onClick={onClose}
            />

            {/* Drawer */}
            <div className={`side-menu-drawer ${isOpen ? 'open' : ''}`}>
                <div style={{ display: 'flex', justifyContent: 'flex-end', padding: '20px' }}>
                    <button onClick={onClose} className="quick-link-chip" style={{ border: 'none', background: 'transparent', fontSize: '1.5rem' }}>
                        ✕
                    </button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', padding: '0 20px' }}>
                    <h2 style={{ margin: '0 0 10px 0', borderBottom: '1px solid var(--panel-border)', paddingBottom: '10px' }}>Menu</h2>

                    <Link to="/stats" className="menu-item" onClick={onClose}>
                        <span style={{ fontSize: '1.2rem' }}>📊</span> Popular Places
                    </Link>

                    <a href="http://3.0.28.161:8000/monitor/" target="_blank" rel="noopener noreferrer" className="menu-item" onClick={onClose}>
                        <span style={{ fontSize: '1.2rem' }}>🚀</span> Training Monitor
                    </a>

                    <Link to="/settings" className="menu-item" onClick={onClose}>
                        <span style={{ fontSize: '1.2rem' }}>⚙️</span> Settings
                    </Link>

                    <Link to="/about" className="menu-item" onClick={onClose}>
                        <span style={{ fontSize: '1.2rem' }}>ℹ️</span> About
                    </Link>
                </div>

            </div>
        </>
    );
};

export default SideMenu;
