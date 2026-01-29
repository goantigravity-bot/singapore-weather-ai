import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider } from '../context/ConfigContext';
import SettingsPage from '../pages/SettingsPage';

// 包装组件以提供必要的 Context
const renderWithProviders = (component: React.ReactElement) => {
    return render(
        <ConfigProvider>
            <BrowserRouter>
                {component}
            </BrowserRouter>
        </ConfigProvider>
    );
};

describe('SettingsPage', () => {
    it('renders configuration title', () => {
        renderWithProviders(<SettingsPage />);
        expect(screen.getByText('Configuration')).toBeInTheDocument();
    });

    it('renders all weather metric toggles', () => {
        renderWithProviders(<SettingsPage />);

        expect(screen.getByText('Rainfall Prediction')).toBeInTheDocument();
        expect(screen.getByText('Temperature')).toBeInTheDocument();
        expect(screen.getByText('Humidity')).toBeInTheDocument();
        expect(screen.getByText('PM2.5 (Air Quality)')).toBeInTheDocument();
    });

    it('renders map display options', () => {
        renderWithProviders(<SettingsPage />);

        expect(screen.getByText('Map Display Options')).toBeInTheDocument();
        expect(screen.getByText('Interpolation Triangle')).toBeInTheDocument();
        expect(screen.getByText('Weather Station Markers')).toBeInTheDocument();
    });

    it('renders back button', () => {
        renderWithProviders(<SettingsPage />);
        expect(screen.getByText('← 返回')).toBeInTheDocument();
    });
});
