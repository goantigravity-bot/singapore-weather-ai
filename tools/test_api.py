import pytest
from fastapi.testclient import TestClient
from api import app

@pytest.fixture(scope="module")
def client():
    # Use context manager to trigger startup/shutdown events
    with TestClient(app) as c:
        yield c

def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_predict_location(client):
    """Test prediction with a named location."""
    # We use a known location from dummy data or ensure mock
    # For integration test, we expect the system to run key paths
    response = client.get("/predict?location=Marina Bay Sands")
    assert response.status_code == 200
    data = response.json()
    assert "forecast" in data
    assert "rainfall_mm_next_10min" in data["forecast"]
    assert "nearest_station" in data
    assert data["nearest_station"]["id"] is not None

def test_predict_coordinates(client):
    """Test prediction with lat/lon."""
    response = client.get("/predict?lat=1.35&lon=103.8")
    assert response.status_code == 200
    data = response.json()
    assert "location_query" in data
    assert "1.35,103.8" in data["location_query"]
    assert "forecast" in data

def test_invalid_params(client):
    """Test validation error when no params provided."""
    response = client.get("/predict")
    # Our API returns 400 if params are missing
    assert response.status_code == 400
