# Singapore Weather AI - Deployment & Testing Guide

## 1. Local Development (Optional)

To run the API locally without Docker:

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python -m uvicorn api:app --reload
```

## 2. Docker Deployment

The application is containerized using Docker. This is the recommended way to deploy.

### Build the Image
```bash
docker build -f Dockerfile.api -t singapore-weather-api .
```

### Run the Container
Run the container, exposing internal port 8000 to your host machine.

```bash
docker run -d -p 8000:8000 --name weather-api singapore-weather-api
```

### Verify Running Container
```bash
curl http://localhost:8000/health
# Output: {"status":"ok"}
```

## 3. Testing

We use `pytest` for automated testing.

### Run Tests Locally
```bash
pytest test_api.py
```

### Run Tests inside Docker
You can also run tests inside the container image to ensure the environment is correct.

```bash
docker run --rm singapore-weather-api pytest test_api.py
```

## 4. API Usage

### Endpoint: `GET /predict`

**Parameters:**
- `location` (string): Address or Place Name (e.g., "Marina Bay Sands")
- `lat` (float): Latitude
- `lon` (float): Longitude

**Examples:**

1. **By Location Name:**
   ```bash
   curl "http://localhost:8000/predict?location=Marina%20Bay%20Sands"
   ```

2. **By Coordinates:**
   ```bash
   curl "http://localhost:8000/predict?lat=1.35&lon=103.8"
   ```
