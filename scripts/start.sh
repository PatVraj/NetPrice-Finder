#!/bin/bash
# =============================================================================
# SSIP - Quick Start Script
# =============================================================================
# This script helps you get SSIP up and running quickly.
# =============================================================================

set -e

echo "🛡️  SSIP - Sovereign Smart Intelligence Platform"
echo "================================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
echo "📋 Checking prerequisites..."

# Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed. Please install Docker first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker found${NC}"

# Docker Compose
if ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose V2 is not available. Please update Docker.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose found${NC}"

# NVIDIA GPU (optional but recommended)
if command -v nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✓ NVIDIA GPU detected${NC}"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
    echo -e "${YELLOW}⚠ No NVIDIA GPU detected. Some features may be limited.${NC}"
fi

# NVIDIA Container Toolkit
if docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✓ NVIDIA Container Toolkit working${NC}"
else
    echo -e "${YELLOW}⚠ NVIDIA Container Toolkit not configured. GPU features will be disabled.${NC}"
fi

echo ""

# Check for .env file
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    
    # Generate random keys
    FIREFLY_KEY=$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 32)
    MYSQL_ROOT_PW=$(head -c 16 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 16)
    MYSQL_PW=$(head -c 16 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 16)
    
    # Update .env with generated values (Linux/Mac compatible)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/CHANGE_ME_GENERATE_32_CHAR_KEY!!/$FIREFLY_KEY/" .env
        sed -i '' "s/CHANGE_ME_ROOT_PASSWORD/$MYSQL_ROOT_PW/" .env
        sed -i '' "s/CHANGE_ME_DB_PASSWORD/$MYSQL_PW/" .env
    else
        sed -i "s/CHANGE_ME_GENERATE_32_CHAR_KEY!!/$FIREFLY_KEY/" .env
        sed -i "s/CHANGE_ME_ROOT_PASSWORD/$MYSQL_ROOT_PW/" .env
        sed -i "s/CHANGE_ME_DB_PASSWORD/$MYSQL_PW/" .env
    fi
    
    echo -e "${GREEN}✓ .env file created with secure random keys${NC}"
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi

echo ""
echo "🚀 Starting SSIP services..."
echo ""

# Build and start
docker compose build
docker compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check service status
echo ""
echo "📊 Service Status:"
docker compose ps

echo ""
echo "================================================="
echo -e "${GREEN}🎉 SSIP is starting up!${NC}"
echo ""
echo "Access the dashboard at: http://localhost:8080"
echo "Firefly III at: http://localhost:8081"
echo "Ollama API at: http://localhost:11434"
echo ""
echo "To pull an LLM model, run:"
echo "  docker compose exec intelligence-core ollama pull llama3.1:8b"
echo ""
echo "To view logs:"
echo "  docker compose logs -f"
echo ""
echo "To stop:"
echo "  docker compose down"
echo "================================================="
