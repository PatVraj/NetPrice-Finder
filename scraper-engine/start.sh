#!/bin/bash
# =============================================================================
# SSIP Scraper Engine Startup Script
# =============================================================================

set -e

echo "Starting Xvfb virtual display..."
Xvfb :99 -screen 0 1920x1080x24 -ac +extension GLX +render -noreset &
XVFB_PID=$!

# Wait for Xvfb to start
sleep 2

# Verify display is working
echo "Display: $DISPLAY"
if ! xdpyinfo -display :99 >/dev/null 2>&1; then
    echo "WARNING: Display :99 may not be ready"
fi

echo "Starting scraper engine..."
exec python run_scraper.py
