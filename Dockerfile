# Base image with Python 3.10
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for some python libs)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Make pipeline executable
RUN chmod +x run_pipeline.sh

# Default command: Run the pipeline
CMD ["./run_pipeline.sh"]
