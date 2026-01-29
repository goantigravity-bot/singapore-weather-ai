import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import AboutPage from '../pages/AboutPage';

const renderWithRouter = (component: React.ReactElement) => {
    return render(
        <BrowserRouter>
            {component}
        </BrowserRouter>
    );
};

describe('AboutPage', () => {
    it('renders app title', () => {
        renderWithRouter(<AboutPage />);
        expect(screen.getByText('Singapore Weather AI')).toBeInTheDocument();
    });

    it('renders version badge', () => {
        renderWithRouter(<AboutPage />);
        expect(screen.getByText('v0.5')).toBeInTheDocument();
    });

    it('renders app description', () => {
        renderWithRouter(<AboutPage />);
        expect(screen.getByText(/real-time weather forecasting/i)).toBeInTheDocument();
    });

    it('renders copyright notice', () => {
        renderWithRouter(<AboutPage />);
        expect(screen.getByText(/© 2026 Singapore Weather AI/)).toBeInTheDocument();
    });

    it('renders close button', () => {
        renderWithRouter(<AboutPage />);
        expect(screen.getByText('❌')).toBeInTheDocument();
    });

    it('renders weather icon', () => {
        renderWithRouter(<AboutPage />);
        expect(screen.getByText('🌦️')).toBeInTheDocument();
    });
});
