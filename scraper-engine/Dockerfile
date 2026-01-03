# =============================================================================
# SSIP Scraper Engine - Playwright + Xvfb + GPU
# =============================================================================
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

LABEL maintainer="SSIP Project"
LABEL description="GPU-accelerated Playwright scraper with Xvfb for WebGL masquerading"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DISPLAY=:99 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies for GPU + Xvfb
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11-utils \
    xauth \
    libgl1-mesa-dri \
    libgl1-mesa-glx \
    libegl1-mesa \
    libgles2-mesa \
    libvulkan1 \
    mesa-vulkan-drivers \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers with dependencies
RUN playwright install chromium --with-deps

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data /app/screenshots

# Create startup script
RUN echo '#!/bin/bash\n\
# Start Xvfb with GPU-friendly settings\n\
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &\n\
sleep 2\n\
# Verify display\n\
echo "Display: $DISPLAY"\n\
# Start the scraper\n\
exec python run_scraper.py\n\
' > /app/start.sh && chmod +x /app/start.sh

# Expose API port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run with Xvfb
CMD ["/app/start.sh"]
