import React, { useState } from 'react';
import { LABELS } from '../i18n/labels';

interface SmartResultProps {
    result: {
        location: string;
        recommendation: string;
        reason: string;
        status_color: string;
        max_rainfall: number;
        details: any[];
        parsed: {
            activity: string;
            start_hour: number;
            end_hour: number;
        }
    } | null;
    onClose: () => void;
}

const SmartResultCard: React.FC<SmartResultProps> = ({ result, onClose }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    if (!result) return null;

    const colorMap: Record<string, string> = {
        'green': '#4caf50',
        'orange': '#ff9800',
        'red': '#f44336'
    };

    const bannerColor = colorMap[result.status_color] || '#4caf50';

    return (
        <div style={{
            position: 'absolute',
            top: '70px',
            left: '50%',
            transform: 'translateX(-50%)',
            width: '90%',
            maxWidth: '400px',
            backgroundColor: 'rgba(20, 30, 48, 0.95)',
            backdropFilter: 'blur(10px)',
            borderRadius: '16px',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
            border: `1px solid ${bannerColor}`,
            zIndex: 2000,
            color: 'white',
            overflow: 'hidden',
            animation: 'fadeIn 0.3s ease-out'
        }}>
            {/* Header */}
            <div style={{
                backgroundColor: bannerColor,
                padding: '12px 16px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
            }}>
                <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 600 }}>
                    {result.recommendation}
                </h3>
                <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'white', fontSize: '1.2rem', cursor: 'pointer' }}>×</button>
            </div>

            {/* Body */}
            <div style={{ padding: '16px' }}>
                <div style={{ marginBottom: '12px' }}>
                    <span style={{ opacity: 0.7, fontSize: '0.9rem' }}>{LABELS.smartResult.query}: </span>
                    <span style={{ fontWeight: 500 }}>{result.parsed.activity} @ {result.location}</span>
                    <div style={{ fontSize: '0.85rem', opacity: 0.6 }}>
                        {LABELS.smartResult.time}: {result.parsed.start_hour}:00 - {result.parsed.end_hour}:00
                    </div>
                </div>

                <div style={{ fontSize: '1rem', marginBottom: '16px', lineHeight: '1.4' }}>
                    {result.reason}
                </div>

                {/* 展开/折叠按钮 */}
                <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    style={{
                        width: '100%',
                        padding: '8px 12px',
                        backgroundColor: 'rgba(255,255,255,0.1)',
                        border: '1px solid rgba(255,255,255,0.2)',
                        borderRadius: '8px',
                        color: 'white',
                        fontSize: '0.9rem',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '8px',
                        transition: 'all 0.2s ease',
                        marginBottom: isExpanded ? '12px' : '0'
                    }}
                    onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.15)';
                    }}
                    onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = 'rgba(255,255,255,0.1)';
                    }}
                >
                    <span>{isExpanded ? LABELS.smartResult.hideDetails : LABELS.smartResult.showDetails}</span>
                    <span style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.3s ease' }}>▼</span>
                </button>

                {/* 路径详情 - 仅在展开时显示 */}
                {isExpanded && (
                    <div style={{
                        maxHeight: '150px',
                        overflowY: 'auto',
                        background: 'rgba(0,0,0,0.2)',
                        borderRadius: '8px',
                        padding: '8px',
                        animation: 'slideDown 0.3s ease-out'
                    }}>
                        {result.details.map((pt, idx) => (
                            <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '4px', paddingBottom: '4px', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                <span>{LABELS.smartResult.point} {pt.point_index}</span>
                                <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <span>{pt.icon}</span>
                                    <span style={{ color: pt.is_risky ? '#ff6b6b' : '#69db7c' }}>
                                        {pt.rainfall > 0 ? `${pt.rainfall}mm` : LABELS.smartResult.dry}
                                    </span>
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default SmartResultCard;
