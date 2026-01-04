"""
SSIP - Sovereign Smart Intelligence Platform
NiceGUI Frontend Application

This is the main entry point for the frontend dashboard.
"""

import os
from nicegui import ui, app
import httpx
import redis.asyncio as redis
import asyncio
from contextlib import asynccontextmanager
import base64
from typing import Optional
import json

# =============================================================================
# Configuration
# =============================================================================

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
SCRAPER_API_URL = os.getenv("SCRAPER_API_URL", "http://localhost:5000")
FIREFLY_API_URL = os.getenv("FIREFLY_API_URL", "http://localhost:8081")

# =============================================================================
# Application State
# =============================================================================

class AppState:
    """Global application state."""
    redis_client: Optional[redis.Redis] = None
    scraper_frame: str = ""
    is_scraping: bool = False
    command_history: list = []

state = AppState()

# =============================================================================
# Redis Connection
# =============================================================================

async def init_redis() -> Optional[redis.Redis]:
    """Initialize Redis connection."""
    try:
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=False
        )
        await client.ping()
        print(f"✅ Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        return client
    except Exception as e:
        print(f"⚠️ Redis connection failed: {e}")
        return None

# =============================================================================
# UI Components
# =============================================================================

def create_header():
    """Create the application header."""
    with ui.header().classes('bg-gradient-to-r from-blue-900 to-purple-900'):
        with ui.row().classes('w-full items-center'):
            ui.label('🛡️ SSIP').classes('text-2xl font-bold text-white')
            ui.label('Sovereign Smart Intelligence Platform').classes('text-gray-300 ml-4')
            ui.space()
            with ui.row().classes('gap-2'):
                status_indicator = ui.label('●').classes('text-green-400')
                ui.label('System Online').classes('text-gray-300 text-sm')

def create_command_bar():
    """Create the unified command input bar."""
    with ui.card().classes('w-full mb-4'):
        ui.label('🔍 Command Center').classes('text-lg font-semibold mb-2')
        with ui.row().classes('w-full gap-2'):
            command_input = ui.input(
                placeholder='Enter URL, search query, or ask a question...'
            ).classes('flex-grow').props('outlined dense')
            
            async def process_command():
                command = command_input.value
                if not command:
                    ui.notify('Please enter a command', type='warning')
                    return
                
                state.command_history.append(command)
                ui.notify(f'Processing: {command}', type='info')
                
                # Route command based on intent
                await route_command(command)
                command_input.value = ''
            
            ui.button('Execute', on_click=process_command).props('color=primary')
            ui.button('🎤', on_click=lambda: ui.notify('Voice input coming soon!')).props('flat')

async def route_command(command: str):
    """Route command to appropriate handler based on intent."""
    # Check if it's a URL
    if command.startswith(('http://', 'https://')):
        await trigger_scraper(command)
        return
    
    # Otherwise, ask the LLM for intent classification
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{OLLAMA_API_URL}/api/generate",
                json={
                    "model": "llama3.1:8b",
                    "prompt": f"""Classify this user command into one of these categories:
                    - SCRAPE: User wants to visit a website or check prices
                    - QUERY: User wants to search their financial data
                    - CHAT: User is asking a general question
                    
                    Command: {command}
                    
                    Reply with only the category name.""",
                    "stream": False
                }
            )
            if response.status_code == 200:
                result = response.json()
                intent = result.get("response", "CHAT").strip().upper()
                ui.notify(f'Intent detected: {intent}', type='info')
            else:
                ui.notify('Could not classify command, treating as chat', type='warning')
    except Exception as e:
        ui.notify(f'LLM unavailable: {str(e)}', type='warning')

async def trigger_scraper(url: str):
    """Trigger the scraper engine to visit a URL."""
    ui.notify(f'Starting scraper for: {url}', type='info')
    state.is_scraping = True
    
    try:
        if state.redis_client:
            await state.redis_client.publish('scraper:commands', json.dumps({
                'action': 'navigate',
                'url': url
            }))
    except Exception as e:
        ui.notify(f'Scraper error: {str(e)}', type='negative')
        state.is_scraping = False

def create_visual_debugger():
    """Create the visual debugger panel for scraper output."""
    with ui.card().classes('w-full'):
        ui.label('👁️ Visual Debugger').classes('text-lg font-semibold mb-2')
        
        # Placeholder for scraper video feed
        with ui.column().classes('w-full items-center'):
            scraper_image = ui.interactive_image(
                source='https://via.placeholder.com/800x450?text=Scraper+Feed',
                cross=True
            ).classes('w-full max-w-4xl border rounded')
            
            async def on_click(e):
                """Handle clicks on the scraper image for HITL interaction."""
                if state.redis_client and state.is_scraping:
                    await state.redis_client.publish('scraper:commands', json.dumps({
                        'action': 'click',
                        'x': e.args['image_x'],
                        'y': e.args['image_y']
                    }))
                    ui.notify(f'Click sent: ({e.args["image_x"]}, {e.args["image_y"]})')
            
            scraper_image.on('mouse', on_click)
            
            with ui.row().classes('gap-4 mt-2'):
                ui.button('⏸️ Pause', on_click=lambda: ui.notify('Paused'))
                ui.button('📸 Screenshot', on_click=lambda: ui.notify('Screenshot saved'))
                ui.button('🔄 Refresh', on_click=lambda: ui.notify('Refreshing...'))

def create_dashboard_panels():
    """Create the main dashboard panels."""
    with ui.row().classes('w-full gap-4'):
        # Left Panel - Quick Actions
        with ui.card().classes('w-1/3'):
            ui.label('⚡ Quick Actions').classes('text-lg font-semibold mb-2')
            with ui.column().classes('gap-2'):
                ui.button('Check Cashback Rates', on_click=lambda: ui.notify('Checking rates...')).classes('w-full')
                ui.button('Upload Bank Statement', on_click=lambda: ui.notify('Upload coming soon')).classes('w-full')
                ui.button('View Transactions', on_click=lambda: ui.notify('Transactions...')).classes('w-full')
                ui.button('Optimize Card Usage', on_click=lambda: ui.notify('Analyzing...')).classes('w-full')
        
        # Middle Panel - Stats
        with ui.card().classes('w-1/3'):
            ui.label('📊 Financial Overview').classes('text-lg font-semibold mb-2')
            with ui.column().classes('gap-2'):
                with ui.row().classes('justify-between'):
                    ui.label('Total Cashback Earned:')
                    ui.label('$0.00').classes('font-bold text-green-500')
                with ui.row().classes('justify-between'):
                    ui.label('Pending Rewards:')
                    ui.label('$0.00').classes('font-bold text-yellow-500')
                with ui.row().classes('justify-between'):
                    ui.label('Missed Opportunities:')
                    ui.label('$0.00').classes('font-bold text-red-500')
        
        # Right Panel - Recent Activity
        with ui.card().classes('w-1/3'):
            ui.label('📜 Recent Activity').classes('text-lg font-semibold mb-2')
            with ui.column().classes('gap-1'):
                ui.label('No recent activity').classes('text-gray-400 italic')

def create_footer():
    """Create the application footer."""
    with ui.footer().classes('bg-gray-800'):
        with ui.row().classes('w-full justify-between items-center'):
            ui.label('SSIP v0.2.0').classes('text-gray-400 text-sm')
            with ui.row().classes('gap-4'):
                ui.link('Documentation', '/docs').classes('text-gray-400 text-sm')
                ui.link('Settings', '/settings').classes('text-gray-400 text-sm')

# =============================================================================
# Pages
# =============================================================================

@ui.page('/')
async def main_page():
    """Main dashboard page."""
    # Initialize Redis
    state.redis_client = await init_redis()
    
    # Dark mode by default
    ui.dark_mode().enable()
    
    # Build the UI
    create_header()
    
    with ui.column().classes('w-full p-4 gap-4'):
        create_command_bar()
        create_visual_debugger()
        create_dashboard_panels()
    
    create_footer()

@ui.page('/health')
async def health_check():
    """Health check endpoint for Docker."""
    return {'status': 'healthy', 'service': 'app-frontend'}

@ui.page('/docs')
def docs_page():
    """Documentation page."""
    ui.dark_mode().enable()
    create_header()
    with ui.column().classes('w-full p-4'):
        ui.label('📚 Documentation').classes('text-2xl font-bold mb-4')
        ui.markdown('''
        ## SSIP - Sovereign Smart Intelligence Platform
        
        ### Quick Start
        1. Enter a URL or search query in the Command Center
        2. Watch the Visual Debugger for real-time scraping
        3. Review extracted data in the dashboard
        
        ### Commands
        - **URL**: Direct navigation to a website
        - **"best cashback for [store]"**: Find optimal cashback rates
        - **"upload statement"**: Process bank statement PDF
        ''')
    create_footer()

# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        host='0.0.0.0',
        port=8080,
        title='SSIP Dashboard',
        favicon='🛡️',
        reload=False,
        show=False
    )
