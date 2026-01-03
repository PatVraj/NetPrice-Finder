# =============================================================================
# SSIP - Quick Start Script (Windows PowerShell)
# =============================================================================
# This script helps you get SSIP up and running quickly on Windows.
# Run with: .\scripts\start.ps1
# =============================================================================

Write-Host "🛡️  SSIP - Sovereign Smart Intelligence Platform" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Host "📋 Checking prerequisites..." -ForegroundColor Yellow

# Docker
try {
    docker --version | Out-Null
    Write-Host "✓ Docker found" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker is not installed. Please install Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Docker Compose
try {
    docker compose version | Out-Null
    Write-Host "✓ Docker Compose found" -ForegroundColor Green
} catch {
    Write-Host "❌ Docker Compose V2 is not available. Please update Docker Desktop." -ForegroundColor Red
    exit 1
}

# NVIDIA GPU
try {
    $gpuInfo = nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null
    if ($gpuInfo) {
        Write-Host "✓ NVIDIA GPU detected: $gpuInfo" -ForegroundColor Green
    }
} catch {
    Write-Host "⚠ No NVIDIA GPU detected. Some features may be limited." -ForegroundColor Yellow
}

Write-Host ""

# Check for .env file
if (-not (Test-Path ".env")) {
    Write-Host "📝 Creating .env file from template..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    
    # Generate random keys
    $chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    $fireflyKey = -join ((1..32) | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
    $mysqlRootPw = -join ((1..16) | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
    $mysqlPw = -join ((1..16) | ForEach-Object { $chars[(Get-Random -Maximum $chars.Length)] })
    
    # Update .env with generated values
    $content = Get-Content ".env"
    $content = $content -replace "CHANGE_ME_GENERATE_32_CHAR_KEY!!", $fireflyKey
    $content = $content -replace "CHANGE_ME_ROOT_PASSWORD", $mysqlRootPw
    $content = $content -replace "CHANGE_ME_DB_PASSWORD", $mysqlPw
    $content | Set-Content ".env"
    
    Write-Host "✓ .env file created with secure random keys" -ForegroundColor Green
} else {
    Write-Host "✓ .env file exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "🚀 Starting SSIP services..." -ForegroundColor Cyan
Write-Host ""

# Build and start
docker compose build
docker compose up -d

Write-Host ""
Write-Host "⏳ Waiting for services to be healthy..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Check service status
Write-Host ""
Write-Host "📊 Service Status:" -ForegroundColor Cyan
docker compose ps

Write-Host ""
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "🎉 SSIP is starting up!" -ForegroundColor Green
Write-Host ""
Write-Host "Access the dashboard at: http://localhost:8080" -ForegroundColor White
Write-Host "Firefly III at: http://localhost:8081" -ForegroundColor White
Write-Host "Ollama API at: http://localhost:11434" -ForegroundColor White
Write-Host ""
Write-Host "To pull an LLM model, run:" -ForegroundColor Yellow
Write-Host "  docker compose exec intelligence-core ollama pull llama3.1:8b" -ForegroundColor White
Write-Host ""
Write-Host "To view logs:" -ForegroundColor Yellow
Write-Host "  docker compose logs -f" -ForegroundColor White
Write-Host ""
Write-Host "To stop:" -ForegroundColor Yellow
Write-Host "  docker compose down" -ForegroundColor White
Write-Host "=================================================" -ForegroundColor Cyan
