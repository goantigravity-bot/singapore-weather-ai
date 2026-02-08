FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (for curl/aws-cli if needed, or just python)
# bulk_download script uses curl/wget?
RUN apt-get update && apt-get install -y curl unzip && rm -rf /var/lib/apt/lists/*

# Install AWS CLI (v2)
RUN curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" \
    && unzip awscliv2.zip \
    && ./aws/install \
    && rm -rf aws awscliv2.zip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x bulk_download_to_s3_parallel.sh

CMD ["python", "download_manager.py"]
