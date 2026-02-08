FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
# libgl1-mesa-glx removed as opencv is not used.
# git might be needed if pip install from git? No.
# Upgrade pip just in case
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create data directories
RUN mkdir -p /app/data/satellite_data /app/data/processed_data /app/data/processed_images

COPY . .

# Set WORK_DIR env
ENV WORK_DIR=/app/data

CMD ["python", "training_service.py"]
