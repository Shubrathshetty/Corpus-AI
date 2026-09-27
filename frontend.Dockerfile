# Use official Python lightweight image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Ensure /app is in python import path
ENV PYTHONPATH=/app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install lightweight frontend dependencies directly with aggressive retries
RUN pip install --no-cache-dir --retries 10 --default-timeout=1000 --index-url https://pypi.org/simple/ "six==1.17.0"
RUN pip install --no-cache-dir --retries 10 --default-timeout=1000 --index-url https://pypi.org/simple/ \
    "streamlit>=1.37.0,<2.0.0" \
    "requests>=2.31.0,<3.0.0" \
    "plotly>=5.0.0,<6.0.0"

# Copy frontend code
COPY frontend/ frontend/

# Expose Streamlit default port
EXPOSE 8501

# Run the Streamlit app
# We specify the address as 0.0.0.0 so it's accessible from outside the container
CMD ["streamlit", "run", "frontend/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
