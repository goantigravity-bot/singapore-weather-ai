FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Frontend Build (Assume it's in a 'frontend_dist' folder context)
# For now, we assume we mount it or copy it during build
# COPY frontend_dist /app/frontend_dist 

COPY . .

# Create data directories
RUN mkdir -p /app/satellite_data

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
