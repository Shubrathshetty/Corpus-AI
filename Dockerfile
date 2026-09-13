# Use official Python lightweight image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (needed for python-multipart, passlib, etc. if compiling from source)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file and install dependencies
COPY requirements.txt .

# Pre-install lightweight CPU-only PyTorch with retries to avoid network packet drops
RUN pip install --no-cache-dir --retries 5 --default-timeout=1000 "torch==2.3.1" --index-url https://download.pytorch.org/whl/cpu

# Install remaining project dependencies
RUN pip install --no-cache-dir --default-timeout=1000 -r requirements.txt

# Copy application code
COPY app/ app/

# Create a data directory for local sqlite/chromadb/uploads
# This should ideally be mapped to a volume in docker-compose
RUN mkdir -p /app/data

# Expose the API port
EXPOSE 8000

# Default command to run the FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
