FROM python:3.12-slim

# Install system dependencies including FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 22+ (required by yt-dlp-ejs; Node 20 is too old)
RUN curl -fsSL https://nodejs.org/dist/v22.10.0/node-v22.10.0-linux-x64.tar.xz \
    | tar -xJ -C /usr/local --strip-components=1
ENV PATH="/usr/local/bin:${PATH}"

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
