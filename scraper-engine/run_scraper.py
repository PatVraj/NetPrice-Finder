"""
SSIP - Sovereign Smart Intelligence Platform
Scraper Engine - Playwright Visual Scraper

This module provides GPU-accelerated browser automation with
real-time visual streaming for debugging and HITL interaction.
"""

import os
import asyncio
import json
import base64
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis.asyncio as redis
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from playwright_stealth import Stealth
import structlog

# =============================================================================
# Configuration
# =============================================================================

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
STREAM_FPS = int(os.getenv("SCRAPER_STREAM_FPS", 15))
SCREENSHOT_QUALITY = int(os.getenv("SCRAPER_SCREENSHOT_QUALITY", 50))
VIEWPORT_WIDTH = int(os.getenv("SCRAPER_VIEWPORT_WIDTH", 1920))
VIEWPORT_HEIGHT = int(os.getenv("SCRAPER_VIEWPORT_HEIGHT", 1080))

# Initialize structured logging
logger = structlog.get_logger()

# =============================================================================
# Request/Response Models
# =============================================================================

class NavigateRequest(BaseModel):
    url: str
    wait_for: str = "networkidle"
    timeout: int = 30000

class ClickRequest(BaseModel):
    x: int
    y: int

class ScrapeResult(BaseModel):
    url: str
    title: str
    content: Optional[str] = None
    screenshot: Optional[str] = None

# =============================================================================
# Scraper Engine
# =============================================================================

class ScraperEngine:
    """
    GPU-accelerated Playwright scraper with real-time streaming.
    
    Features:
    - Headful mode with Xvfb for anti-bot evasion
    - WebGL fingerprinting via GPU passthrough
    - Real-time screenshot streaming to Redis
    - Human-in-the-Loop (HITL) click relay
    """
    
    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.redis_client: Optional[redis.Redis] = None
        self.streaming = False
        self._stream_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """Initialize Playwright and Redis connections."""
        logger.info("Initializing Scraper Engine...")
        
        # Connect to Redis
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=False
            )
            await self.redis_client.ping()
            logger.info("Connected to Redis", host=REDIS_HOST, port=REDIS_PORT)
        except Exception as e:
            logger.warning("Redis connection failed", error=str(e))
            self.redis_client = None
        
        # Initialize Playwright
        self.playwright = await async_playwright().start()
        
        # Launch browser with GPU-enabled flags
        self.browser = await self.playwright.chromium.launch(
            headless=False,  # CRITICAL: Must be False for WebGL masquerading
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--enable-webgl',
                '--use-gl=desktop',  # Use desktop OpenGL (GPU)
                '--enable-gpu-rasterization',
                '--enable-accelerated-2d-canvas',
                '--ignore-gpu-blocklist',
                '--enable-features=VaapiVideoDecoder',
            ]
        )
        
        # Create context with realistic settings
        self.context = await self.browser.new_context(
            viewport={'width': VIEWPORT_WIDTH, 'height': VIEWPORT_HEIGHT},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York',
        )
        
        # Create page and apply stealth patches
        self.page = await self.context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(self.page)
        
        logger.info("Scraper Engine initialized successfully")
        
        # Start listening for commands
        if self.redis_client:
            asyncio.create_task(self._listen_for_commands())
    
    async def shutdown(self):
        """Clean shutdown of the scraper."""
        logger.info("Shutting down Scraper Engine...")
        self.streaming = False
        
        if self._stream_task:
            self._stream_task.cancel()
        
        if self.page:
            await self.page.close()
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        if self.redis_client:
            await self.redis_client.close()
        
        logger.info("Scraper Engine shutdown complete")
    
    async def navigate(self, url: str, wait_for: str = "networkidle", timeout: int = 30000) -> ScrapeResult:
        """Navigate to a URL and start streaming."""
        if not self.page:
            raise RuntimeError("Scraper not initialized")
        
        logger.info("Navigating to URL", url=url)
        
        # Start streaming before navigation
        await self.start_streaming()
        
        try:
            await self.page.goto(url, wait_until=wait_for, timeout=timeout)
            title = await self.page.title()
            
            # Take a screenshot
            screenshot_bytes = await self.page.screenshot(
                type='jpeg',
                quality=SCREENSHOT_QUALITY
            )
            screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            
            logger.info("Navigation complete", url=url, title=title)
            
            return ScrapeResult(
                url=url,
                title=title,
                screenshot=screenshot_b64
            )
        except Exception as e:
            logger.error("Navigation failed", url=url, error=str(e))
            raise
    
    async def click_at(self, x: int, y: int):
        """Click at specific coordinates (for HITL interaction)."""
        if not self.page:
            raise RuntimeError("Scraper not initialized")
        
        logger.info("Clicking at coordinates", x=x, y=y)
        await self.page.mouse.click(x, y)
    
    async def start_streaming(self):
        """Start streaming screenshots to Redis."""
        if self.streaming or not self.redis_client:
            return
        
        self.streaming = True
        self._stream_task = asyncio.create_task(self._stream_loop())
        logger.info("Screenshot streaming started", fps=STREAM_FPS)
    
    async def stop_streaming(self):
        """Stop the screenshot stream."""
        self.streaming = False
        if self._stream_task:
            self._stream_task.cancel()
            self._stream_task = None
        logger.info("Screenshot streaming stopped")
    
    async def _stream_loop(self):
        """Continuous screenshot streaming loop."""
        frame_interval = 1.0 / STREAM_FPS
        
        while self.streaming and self.page and self.redis_client:
            try:
                # Capture screenshot
                screenshot_bytes = await self.page.screenshot(
                    type='jpeg',
                    quality=SCREENSHOT_QUALITY
                )
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
                
                # Publish to Redis
                await self.redis_client.publish(
                    'scraper:stream',
                    screenshot_b64
                )
                
                await asyncio.sleep(frame_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Stream frame error", error=str(e))
                await asyncio.sleep(frame_interval)
    
    async def _listen_for_commands(self):
        """Listen for commands from Redis pub/sub."""
        if not self.redis_client:
            return
        
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe('scraper:commands')
        
        logger.info("Listening for commands on scraper:commands")
        
        async for message in pubsub.listen():
            if message['type'] != 'message':
                continue
            
            try:
                command = json.loads(message['data'])
                action = command.get('action')
                
                if action == 'navigate':
                    url = command.get('url')
                    if url:
                        await self.navigate(url)
                elif action == 'click':
                    x = command.get('x', 0)
                    y = command.get('y', 0)
                    await self.click_at(x, y)
                elif action == 'stop':
                    await self.stop_streaming()
                    
            except Exception as e:
                logger.error("Command processing error", error=str(e))

# =============================================================================
# FastAPI Application
# =============================================================================

scraper = ScraperEngine()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    await scraper.initialize()
    yield
    await scraper.shutdown()

app = FastAPI(
    title="SSIP Scraper Engine",
    description="GPU-accelerated visual scraper with real-time streaming",
    version="0.2.0",
    lifespan=lifespan
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "scraper-engine",
        "streaming": scraper.streaming,
        "browser_connected": scraper.browser is not None
    }

@app.post("/navigate", response_model=ScrapeResult)
async def navigate(request: NavigateRequest):
    """Navigate to a URL."""
    try:
        return await scraper.navigate(
            url=request.url,
            wait_for=request.wait_for,
            timeout=request.timeout
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/click")
async def click(request: ClickRequest):
    """Click at specific coordinates."""
    try:
        await scraper.click_at(request.x, request.y)
        return {"status": "clicked", "x": request.x, "y": request.y}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stream/start")
async def start_stream():
    """Start screenshot streaming."""
    await scraper.start_streaming()
    return {"status": "streaming_started"}

@app.post("/stream/stop")
async def stop_stream():
    """Stop screenshot streaming."""
    await scraper.stop_streaming()
    return {"status": "streaming_stopped"}

@app.get("/screenshot")
async def get_screenshot():
    """Get a single screenshot."""
    if not scraper.page:
        raise HTTPException(status_code=503, detail="Scraper not initialized")
    
    screenshot_bytes = await scraper.page.screenshot(type='jpeg', quality=SCREENSHOT_QUALITY)
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
    return {"screenshot": screenshot_b64}

# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
