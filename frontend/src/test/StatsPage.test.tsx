import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import axios from 'axios';
import StatsPage from '../pages/StatsPage';

// Mock axios
vi.mock('axios');
const mockedAxios = axios as jest.Mocked<typeof axios>;

const renderWithRouter = (component: React.ReactElement) => {
    return render(
        <BrowserRouter>
            {component}
        </BrowserRouter>
    );
};

describe('StatsPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders page title', () => {
        mockedAxios.get.mockResolvedValueOnce({ data: [] });
        renderWithRouter(<StatsPage />);
        expect(screen.getByText('Popular Places 📊')).toBeInTheDocument();
    });

    it('shows loading state initially', () => {
        mockedAxios.get.mockImplementation(() => new Promise(() => { })); // Never resolves
        renderWithRouter(<StatsPage />);
        expect(screen.getByText('Loading statistics...')).toBeInTheDocument();
    });

    it('shows empty state when no locations', async () => {
        mockedAxios.get.mockResolvedValueOnce({ data: [] });
        renderWithRouter(<StatsPage />);

        await waitFor(() => {
            expect(screen.getByText('No search history yet.')).toBeInTheDocument();
        });
    });

    it('renders location list when data is available', async () => {
        const mockLocations = [
            { name: 'Orchard Road', count: 42 },
            { name: 'Marina Bay', count: 35 },
            { name: 'Sentosa', count: 28 }
        ];
        mockedAxios.get.mockResolvedValueOnce({ data: mockLocations });

        renderWithRouter(<StatsPage />);

        await waitFor(() => {
            expect(screen.getByText('Orchard Road')).toBeInTheDocument();
            expect(screen.getByText('Marina Bay')).toBeInTheDocument();
            expect(screen.getByText('Sentosa')).toBeInTheDocument();
        });
    });

    it('displays search count for each location', async () => {
        const mockLocations = [
            { name: 'Orchard Road', count: 42 }
        ];
        mockedAxios.get.mockResolvedValueOnce({ data: mockLocations });

        renderWithRouter(<StatsPage />);

        await waitFor(() => {
            expect(screen.getByText('42 searches')).toBeInTheDocument();
        });
    });

    it('renders view buttons for each location', async () => {
        const mockLocations = [
            { name: 'Orchard Road', count: 42 },
            { name: 'Marina Bay', count: 35 }
        ];
        mockedAxios.get.mockResolvedValueOnce({ data: mockLocations });

        renderWithRouter(<StatsPage />);

        await waitFor(() => {
            const viewButtons = screen.getAllByText('🗺️ View');
            expect(viewButtons).toHaveLength(2);
        });
    });

    it('renders footer text', async () => {
        mockedAxios.get.mockResolvedValueOnce({ data: [] });
        renderWithRouter(<StatsPage />);

        await waitFor(() => {
            expect(screen.getByText('Top 6 most searched locations')).toBeInTheDocument();
        });
    });

    it('renders close button', () => {
        mockedAxios.get.mockResolvedValueOnce({ data: [] });
        renderWithRouter(<StatsPage />);
        expect(screen.getByText('❌')).toBeInTheDocument();
    });
});
