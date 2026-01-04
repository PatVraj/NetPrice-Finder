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

# Install system dependencies for GPU + Xvfb (Ubuntu 24.04 Noble package names)
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11-utils \
    xauth \
    libgl1-mesa-dri \
    libgl1 \
    libegl1 \
    libgles2 \
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

# Copy startup script and make executable
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Expose API port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run with Xvfb
CMD ["/app/start.sh"]
