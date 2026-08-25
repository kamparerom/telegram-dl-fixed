FROM python:3.12-slim

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    git \
    build-essential \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium

# Copy application source code
COPY . .

# Create directory structures for runtime storage
RUN mkdir -p /app/data/jobs /app/data/cache /app/data/cookies

EXPOSE 8000

CMD ["python", "app/main.py"]
