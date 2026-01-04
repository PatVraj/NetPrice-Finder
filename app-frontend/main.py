"""
Net Price Finder - Frontend Application
Modern, minimalistic NiceGUI dashboard for finding the TRUE cheapest price

Features:
- User authentication (login/register/logout)
- Admin dashboard for retailer data visualization
- Cashback comparison across 5+ platforms
- Credit card reward optimization
"""

import os
from nicegui import ui, app
import httpx
import redis.asyncio as redis
import asyncio
from typing import Optional, List, Dict, Any
import json
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import secrets
import logging

# Import our SQLite database layer
from database import (
    UserDatabase, get_user_database,
    User, UserCard, SearchHistory,
    hash_password, verify_password
)

# =============================================================================
# Configuration
# =============================================================================

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
API_URL = os.getenv("API_URL", "http://localhost:8000")
STORAGE_SECRET = os.getenv("STORAGE_SECRET", "netprice-dev-secret-change-in-production")
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

# =============================================================================
# Data Models
# =============================================================================

@dataclass
class CashbackSearchResult:
    """Result from checking a single cashback platform."""
    platform: str
    rate: float = 0.0
    found: bool = False
    error: Optional[str] = None

@dataclass
class SearchTransparency:
    """Transparency into what was searched and found."""
    cashback_platforms_checked: List[CashbackSearchResult] = field(default_factory=list)
    tax_source: str = "default"
    search_duration_ms: int = 0

@dataclass
class PriceResult:
    """Result from price optimization."""
    product_name: str = ""
    product_price: float = 0.0
    retailer: str = ""
    original_url: str = ""
    coupon_code: Optional[str] = None
    coupon_discount: float = 0.0
    tax: float = 0.0
    tax_rate: float = 0.0
    tax_location: Optional[str] = None
    shipping: float = 0.0
    gross_total: float = 0.0
    cashback_platform: Optional[str] = None
    cashback_percent: float = 0.0
    cashback_value: float = 0.0
    all_cashback_rates: List[dict] = field(default_factory=list)
    card_name: Optional[str] = None
    card_reward_percent: float = 0.0
    card_reward_value: float = 0.0
    net_price: float = 0.0
    total_savings: float = 0.0
    savings_percent: float = 0.0
    search_transparency: Optional[SearchTransparency] = None

@dataclass 
class UserCard:
    """Credit card in user's wallet."""
    name: str
    issuer: str
    base_rate: float
    highlights: List[str] = field(default_factory=list)

@dataclass
class User:
    """User account."""
    id: str
    email: str
    password_hash: str
    is_admin: bool = False
    created_at: str = ""

# =============================================================================
# Application State
# =============================================================================

class AppState:
    """Global application state."""
    redis_client: Optional[redis.Redis] = None
    current_result: Optional[PriceResult] = None
    db: Optional[UserDatabase] = None

state = AppState()

# Initialize database
def init_database():
    """Initialize the SQLite database."""
    state.db = get_user_database()
    
    # Create demo admin user if DEMO_MODE and doesn't exist
    if DEMO_MODE:
        existing = state.db.get_user_by_email("admin@netprice.local")
        if not existing:
            logging.info("🧪 DEMO_MODE enabled - creating demo admin user")
            state.db.create_user(
                email="admin@netprice.local",
                password="admin123",
                is_admin=True
            )

# Initialize on import
init_database()

# =============================================================================
# Authentication Helpers
# =============================================================================

def get_current_user() -> Optional[User]:
    """Get the currently logged in user from database."""
    user_email = app.storage.user.get('email')
    if user_email and state.db:
        return state.db.get_user_by_email(user_email)
    return None

def get_current_user_id() -> Optional[int]:
    """Get the current user's ID."""
    user = get_current_user()
    return user.id if user else None

def is_authenticated() -> bool:
    """Check if user is authenticated."""
    return app.storage.user.get('authenticated', False)

def is_admin() -> bool:
    """Check if current user is admin."""
    user = get_current_user()
    return user.is_admin if user else False

# =============================================================================
# Redis Connection
# =============================================================================

async def init_redis() -> Optional[redis.Redis]:
    """Initialize async Redis connection."""
    try:
        # Using redis.asyncio.Redis - ping() is awaitable
        client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=False)
        # Verify connection with async ping
        await client.ping()
        return client
    except Exception as e:
        logging.warning(f"⚠️ Redis connection failed: {e}")
        return None

# =============================================================================
# API Client
# =============================================================================

async def find_best_price(query: str) -> Optional[PriceResult]:
    """Call the optimizer API to find best price."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            request_data = {"query": query, "include_cashback": True, "include_coupons": True}
            if state.user_tax_rate is not None:
                request_data["user_tax_rate"] = state.user_tax_rate
                request_data["user_location"] = state.user_location
            
            response = await client.post(f"{API_URL}/api/v1/find-best-price", json=request_data)
            if response.status_code == 200:
                data = response.json()
                
                transparency = None
                if data.get("search_transparency"):
                    t = data["search_transparency"]
                    cashback_results = [
                        CashbackSearchResult(
                            platform=c.get("platform", ""),
                            rate=c.get("rate", 0.0),
                            found=c.get("found", False),
                            error=c.get("error")
                        )
                        for c in t.get("cashback_platforms_checked", [])
                    ]
                    transparency = SearchTransparency(
                        cashback_platforms_checked=cashback_results,
                        tax_source=t.get("tax_source", "default"),
                        search_duration_ms=t.get("search_duration_ms", 0)
                    )
                
                result_data = {k: v for k, v in data.items() if k not in ['timestamp', 'search_transparency']}
                result_data['search_transparency'] = transparency
                return PriceResult(**result_data)
    except Exception as e:
        print(f"API Error: {e}")
    return None

async def get_retailer_stats() -> Dict[str, Any]:
    """Fetch retailer stats for admin dashboard."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{API_URL}/api/v1/intelligence/stats")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Stats API Error: {e}")
    return {}

# =============================================================================
# Custom CSS
# =============================================================================

CUSTOM_CSS = """
<style>
    :root {
        --primary: #10b981;
        --surface: #111827;
        --surface-light: #1f2937;
    }
    
    /* Reset and base responsive styles */
    *, *::before, *::after {
        box-sizing: border-box;
    }
    
    html, body {
        margin: 0;
        padding: 0;
        width: 100%;
        min-height: 100vh;
        overflow-x: hidden;
    }
    
    /* Responsive typography */
    html {
        font-size: 16px;
    }
    
    @media (max-width: 640px) {
        html { font-size: 14px; }
    }
    
    /* Glass effect */
    .glass {
        background: rgba(31, 41, 55, 0.8);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    
    /* Hero background */
    .hero-bg {
        background: linear-gradient(135deg, #064e3b 0%, #0f172a 50%, #1e1b4b 100%);
        min-height: calc(100vh - 4rem);
    }
    
    /* Text glow */
    .glow {
        text-shadow: 0 0 30px rgba(16, 185, 129, 0.4);
    }
    
    /* Stat cards */
    .stat-card {
        background: linear-gradient(145deg, #1f2937 0%, #111827 100%);
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    /* Animations */
    .fade-in {
        animation: fadeIn 0.4s ease-out;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* Search box */
    .search-box {
        background: rgba(17, 24, 39, 0.9) !important;
        border: 2px solid rgba(16, 185, 129, 0.2) !important;
        transition: border-color 0.2s !important;
    }
    
    .search-box:focus-within {
        border-color: #10b981 !important;
    }
    
    /* Responsive hero text */
    .hero-title {
        font-size: clamp(2rem, 8vw, 3.75rem);
        line-height: 1.1;
    }
    
    .hero-subtitle {
        font-size: clamp(1rem, 3vw, 1.25rem);
    }
    
    /* Responsive containers */
    .responsive-container {
        width: 100%;
        max-width: 100%;
        padding-left: 1rem;
        padding-right: 1rem;
    }
    
    @media (min-width: 640px) {
        .responsive-container {
            padding-left: 1.5rem;
            padding-right: 1.5rem;
        }
    }
    
    @media (min-width: 1024px) {
        .responsive-container {
            max-width: 1024px;
            margin-left: auto;
            margin-right: auto;
        }
    }
    
    @media (min-width: 1280px) {
        .responsive-container {
            max-width: 1280px;
        }
    }
    
    /* Responsive stat cards grid */
    .stats-grid {
        display: grid;
        grid-template-columns: repeat(1, 1fr);
        gap: 1rem;
    }
    
    @media (min-width: 640px) {
        .stats-grid {
            grid-template-columns: repeat(2, 1fr);
        }
    }
    
    @media (min-width: 1024px) {
        .stats-grid {
            grid-template-columns: repeat(4, 1fr);
        }
    }
    
    /* Responsive tables */
    .q-table {
        width: 100%;
        overflow-x: auto;
    }
    
    /* Mobile nav adjustments */
    @media (max-width: 640px) {
        .nav-links {
            display: none;
        }
        
        .mobile-menu-btn {
            display: block !important;
        }
    }
    
    /* Card responsive padding */
    .card-responsive {
        padding: 1rem;
    }
    
    @media (min-width: 640px) {
        .card-responsive {
            padding: 1.5rem;
        }
    }
    
    /* Flex wrap for mobile */
    .flex-responsive {
        flex-wrap: wrap;
    }
    
    /* Full width inputs on mobile */
    @media (max-width: 640px) {
        .nicegui-input, .nicegui-select {
            width: 100% !important;
        }
    }
</style>
"""

# =============================================================================
# UI Components
# =============================================================================

def create_navbar():
    """Create the navigation bar."""
    with ui.header().classes('bg-gray-900/95 backdrop-blur-md border-b border-gray-800/50 fixed w-full top-0 z-50'):
        with ui.row().classes('w-full max-w-6xl mx-auto px-4 sm:px-6 py-3 items-center justify-between'):
            with ui.link('/', target='_self').classes('no-underline'):
                with ui.row().classes('items-center gap-2'):
                    ui.html('<span class="text-2xl">💰</span>', sanitize=False)
                    ui.label('NetPrice').classes('text-lg sm:text-xl font-bold text-white tracking-tight')
            
            with ui.row().classes('items-center gap-2 sm:gap-4'):
                if is_authenticated():
                    user = get_current_user()
                    # Hide text links on mobile, show on sm+
                    ui.link('Search', '/').classes('hidden sm:block text-gray-400 hover:text-white transition-colors no-underline text-sm')
                    ui.link('Cards', '/cards').classes('hidden sm:block text-gray-400 hover:text-white transition-colors no-underline text-sm')
                    
                    if is_admin():
                        ui.link('Admin', '/admin').classes('hidden sm:block text-emerald-400 hover:text-emerald-300 transition-colors no-underline text-sm font-medium')
                    
                    with ui.button(icon='account_circle').props('flat round size=sm color=gray'):
                        with ui.menu().classes('bg-gray-800'):
                            ui.menu_item(f'{user.email}').props('disable').classes('text-gray-400 text-xs sm:text-sm')
                            ui.separator()
                            # Mobile-only nav items
                            ui.menu_item('Search', lambda: ui.navigate.to('/')).classes('sm:hidden')
                            ui.menu_item('Cards', lambda: ui.navigate.to('/cards')).classes('sm:hidden')
                            if is_admin():
                                ui.menu_item('Admin', lambda: ui.navigate.to('/admin')).classes('sm:hidden')
                            ui.menu_item('Settings', lambda: ui.navigate.to('/settings'))
                            ui.menu_item('Logout', lambda: do_logout())
                else:
                    ui.button('Login', on_click=lambda: ui.navigate.to('/login')).props('flat text-color=white size=sm')
                    ui.button('Sign Up', on_click=lambda: ui.navigate.to('/register')).props('color=primary size=sm unelevated')

def do_logout():
    """Log out the current user."""
    app.storage.user.clear()
    ui.notify('Logged out', type='info')
    ui.navigate.to('/login')

def create_hero_search():
    """Create the hero search section."""
    with ui.element('div').classes('w-full hero-bg min-h-[calc(100vh-4rem)] flex items-center'):
        with ui.column().classes('w-full max-w-3xl mx-auto px-4 sm:px-6 py-12 sm:py-20 items-center'):
            ui.html('<h1 class="hero-title font-bold text-white text-center mb-4 glow tracking-tight">Your True Price</h1>', sanitize=False)
            ui.label('Compare cashback across 5 platforms instantly').classes(
                'hero-subtitle text-gray-400 text-center mb-8 sm:mb-12'
            )
            
            with ui.card().classes('w-full glass rounded-2xl p-2'):
                with ui.row().classes('w-full items-center gap-2'):
                    search_input = ui.input(
                        placeholder='Paste any product URL...'
                    ).classes('flex-grow search-box rounded-xl').props('borderless dense')
                    
                    search_btn = ui.button(icon='arrow_forward').props('color=primary round unelevated')
            
            with ui.column().classes('w-full mt-8 items-center') as loading_area:
                loading_area.visible = False
                ui.spinner('dots', size='lg', color='primary')
                progress_label = ui.label('Analyzing...').classes('text-gray-400 mt-4')
            
            with ui.row().classes('mt-12 sm:mt-20 gap-6 sm:gap-12 flex-wrap justify-center'):
                for icon, val, lbl in [('💵', '5', 'Cashback Sites'), ('💳', '50+', 'Cards Supported'), ('⚡', '<3s', 'Analysis Time')]:
                    with ui.column().classes('items-center min-w-[80px]'):
                        ui.html(f'<span class="text-xl sm:text-2xl">{icon}</span>', sanitize=False)
                        ui.label(val).classes('text-lg sm:text-xl font-bold text-white mt-2')
                        ui.label(lbl).classes('text-gray-500 text-xs sm:text-sm text-center')
            
            async def search():
                query = search_input.value.strip()
                if not query:
                    ui.notify('Enter a product URL', type='warning')
                    return
                
                loading_area.visible = True
                search_btn.disable()
                
                try:
                    progress_label.text = 'Extracting product info...'
                    await asyncio.sleep(0.2)
                    progress_label.text = 'Checking cashback platforms...'
                    
                    result = await find_best_price(query)
                    if result:
                        state.current_result = result
                        
                        # Save to search history
                        user_id = get_current_user_id()
                        if user_id:
                            state.db.add_search_history(
                                user_id=user_id,
                                product_url=query,
                                product_price=result.product_price,
                                net_price=result.net_price,
                                product_name=result.product_name,
                                retailer=result.retailer,
                                total_savings=result.total_savings,
                                best_cashback_platform=result.cashback_platform,
                                best_cashback_rate=result.cashback_percent
                            )
                        
                        ui.navigate.to('/results')
                    else:
                        ui.notify('Could not analyze product', type='warning')
                except Exception as e:
                    ui.notify(str(e), type='negative')
                finally:
                    loading_area.visible = False
                    search_btn.enable()
            
            search_btn.on('click', search)

def create_landing():
    """Create landing page for non-authenticated users."""
    with ui.element('div').classes('w-full hero-bg min-h-[calc(100vh-4rem)] flex items-center justify-center'):
        with ui.column().classes('items-center px-4 sm:px-6 py-12'):
            ui.html('<span class="text-5xl sm:text-6xl mb-4 sm:mb-6">💰</span>', sanitize=False)
            ui.html('<h1 class="hero-title font-bold text-white text-center mb-4 glow tracking-tight">NetPrice Finder</h1>', sanitize=False)
            ui.label('Find the TRUE cheapest price after all savings').classes('hero-subtitle text-gray-400 text-center mb-8 sm:mb-10 max-w-lg px-4')
            
            with ui.row().classes('gap-3 sm:gap-4 flex-wrap justify-center'):
                ui.button('Get Started', on_click=lambda: ui.navigate.to('/register')).props('color=primary size=md unelevated')
                ui.button('Login', on_click=lambda: ui.navigate.to('/login')).props('flat text-color=white size=md')

def create_results():
    """Create results display."""
    if not state.current_result:
        ui.navigate.to('/')
        return
    
    r = state.current_result
    
    with ui.column().classes('w-full max-w-2xl mx-auto px-4 sm:px-6 py-6 sm:py-8 fade-in'):
        ui.button('← Back', on_click=lambda: ui.navigate.to('/')).props('flat color=gray size=sm')
        
        with ui.card().classes('w-full glass rounded-2xl p-4 sm:p-6 mt-4'):
            ui.label(r.retailer.upper()).classes('text-emerald-400 text-xs font-semibold tracking-widest')
            ui.label(r.product_name or 'Product').classes('text-lg sm:text-xl font-bold text-white mt-1 break-words')
            ui.label(f'${r.product_price:.2f}').classes('text-xl sm:text-2xl font-bold text-gray-500 mt-2')
        
        with ui.card().classes('w-full glass rounded-2xl p-4 sm:p-6 mt-4'):
            ui.label('Breakdown').classes('text-sm font-semibold text-gray-400 mb-4 uppercase tracking-wider')
            
            lines = [('Product', f'${r.product_price:.2f}', 'text-white')]
            
            if r.coupon_discount > 0:
                lines.append((f'Coupon', f'-${r.coupon_discount:.2f}', 'text-emerald-400'))
            if r.tax > 0:
                lines.append((f'Tax ({r.tax_location or ""})', f'+${r.tax:.2f}', 'text-gray-400'))
            if r.shipping > 0:
                lines.append(('Shipping', f'+${r.shipping:.2f}', 'text-gray-400'))
            if r.cashback_platform:
                lines.append((f'{r.cashback_platform} ({r.cashback_percent}%)', f'-${r.cashback_value:.2f}', 'text-emerald-400'))
            if r.card_name:
                lines.append((f'{r.card_name}', f'-${r.card_reward_value:.2f}', 'text-blue-400'))
            
            for label, value, color in lines:
                with ui.row().classes('w-full justify-between py-3 border-b border-gray-700/30'):
                    ui.label(label).classes('text-gray-300 text-sm')
                    ui.label(value).classes(f'font-medium {color}')
        
        with ui.card().classes('w-full bg-gradient-to-r from-emerald-900/60 to-teal-900/60 rounded-2xl p-6 mt-4 border border-emerald-800/30'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('Net Price').classes('text-lg text-emerald-200')
                ui.label(f'${r.net_price:.2f}').classes('text-4xl font-bold text-white')
            ui.label(f'You save ${r.total_savings:.2f} ({r.savings_percent:.1f}%)').classes('text-emerald-300 text-sm mt-2')
        
        if r.search_transparency and r.search_transparency.cashback_platforms_checked:
            with ui.expansion('Cashback Comparison', icon='compare_arrows').classes('w-full mt-4'):
                with ui.column().classes('gap-2'):
                    for cb in sorted(r.search_transparency.cashback_platforms_checked, key=lambda x: -x.rate):
                        is_best = r.cashback_platform and cb.platform.lower() == r.cashback_platform.lower()
                        with ui.row().classes('w-full justify-between items-center py-2'):
                            with ui.row().classes('items-center gap-2'):
                                icon_color = 'emerald' if cb.found else 'gray'
                                ui.icon('check_circle' if cb.found else 'cancel', size='xs', color=icon_color)
                                ui.label(cb.platform).classes('text-sm ' + ('text-white' if cb.found else 'text-gray-500'))
                                if is_best:
                                    ui.badge('Best').props('color=positive dense')
                            ui.label(f'{cb.rate}%' if cb.found else '—').classes('text-sm ' + ('text-emerald-400 font-medium' if cb.found else 'text-gray-600'))

def create_login():
    """Create login form."""
    with ui.column().classes('w-full max-w-sm mx-auto px-4 sm:px-6 py-12 sm:py-20 items-center'):
        ui.label('Welcome back').classes('text-2xl sm:text-3xl font-bold text-white mb-2')
        ui.label('Sign in to continue').classes('text-gray-400 mb-6 sm:mb-8')
        
        with ui.card().classes('w-full glass rounded-2xl p-6 sm:p-8'):
            email = ui.input('Email').classes('w-full mb-4')
            password = ui.input('Password', password=True, password_toggle_button=True).classes('w-full mb-6')
            
            btn = ui.button('Sign In').props('color=primary unelevated').classes('w-full')
            
            async def login():
                e, p = email.value.strip(), password.value
                if not e or not p:
                    ui.notify('Fill in all fields', type='warning')
                    return
                user = state.db.authenticate_user(e, p)
                if user:
                    app.storage.user['authenticated'] = True
                    app.storage.user['email'] = user.email
                    app.storage.user['user_id'] = user.id
                    ui.notify('Welcome!', type='positive')
                    ui.navigate.to('/')
                else:
                    ui.notify('Invalid credentials', type='negative')
            
            btn.on('click', login)
        
        with ui.row().classes('mt-6 gap-2'):
            ui.label("No account?").classes('text-gray-400 text-sm')
            ui.link('Sign up', '/register').classes('text-emerald-400 text-sm no-underline')

def create_register():
    """Create registration form."""
    with ui.column().classes('w-full max-w-sm mx-auto px-4 sm:px-6 py-12 sm:py-20 items-center'):
        ui.label('Create account').classes('text-2xl sm:text-3xl font-bold text-white mb-2')
        ui.label('Start saving today').classes('text-gray-400 mb-6 sm:mb-8')
        
        with ui.card().classes('w-full glass rounded-2xl p-6 sm:p-8'):
            email = ui.input('Email').classes('w-full mb-4')
            password = ui.input('Password', password=True, password_toggle_button=True).classes('w-full mb-4')
            confirm = ui.input('Confirm', password=True, password_toggle_button=True).classes('w-full mb-6')
            
            btn = ui.button('Create Account').props('color=primary unelevated').classes('w-full')
            
            async def register():
                e, p, c = email.value.strip(), password.value, confirm.value
                if not e or not p:
                    ui.notify('Fill in all fields', type='warning')
                    return
                if p != c:
                    ui.notify('Passwords do not match', type='warning')
                    return
                
                user = state.db.create_user(email=e, password=p, is_admin=False)
                if not user:
                    ui.notify('Email already registered', type='warning')
                    return
                
                app.storage.user['authenticated'] = True
                app.storage.user['email'] = user.email
                app.storage.user['user_id'] = user.id
                ui.notify('Account created!', type='positive')
                ui.navigate.to('/')
            
            btn.on('click', register)
        
        with ui.row().classes('mt-6 gap-2'):
            ui.label("Have an account?").classes('text-gray-400 text-sm')
            ui.link('Sign in', '/login').classes('text-emerald-400 text-sm no-underline')

async def create_admin():
    """Create admin dashboard with real data from SQLite."""
    if not is_admin():
        ui.navigate.to('/')
        return
    
    # Fetch real stats from API
    stats_data = await get_retailer_stats()
    db_stats = stats_data.get("database", {})
    top_retailers = stats_data.get("top_retailers", [])
    platform_status = stats_data.get("platform_status", [])
    
    with ui.column().classes('w-full max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8'):
        ui.label('Admin Dashboard').classes('text-2xl sm:text-3xl font-bold text-white mb-6 sm:mb-8')
        
        # Stats cards with real data
        total_retailers = db_stats.get("total_retailers", 0)
        total_cashback = db_stats.get("total_cashback_offers", 0)
        total_queries = db_stats.get("total_queries", 0)
        
        with ui.element('div').classes('stats-grid w-full mb-6 sm:mb-8'):
            for label, value, icon, color in [
                ('Retailers', str(total_retailers), 'store', 'emerald'),
                ('Cashback Entries', str(total_cashback), 'attach_money', 'blue'),
                ('Total Queries', f'{total_queries:,}', 'search', 'purple'),
                ('Users', str(state.db.get_user_count()), 'people', 'amber'),
            ]:
                with ui.card().classes('stat-card rounded-xl p-4 sm:p-5'):
                    with ui.row().classes('items-center gap-3 sm:gap-4'):
                        ui.icon(icon, size='md', color=color)
                        with ui.column().classes('gap-0'):
                            ui.label(value).classes('text-xl sm:text-2xl font-bold text-white')
                            ui.label(label).classes('text-gray-400 text-xs')
        
        # Top Retailers table with real data
        with ui.card().classes('w-full glass rounded-xl p-4 sm:p-6'):
            ui.label('Top Retailers').classes('text-base sm:text-lg font-semibold text-white mb-4')
            
            columns = [
                {'name': 'rank', 'label': '#', 'field': 'rank', 'align': 'left'},
                {'name': 'name', 'label': 'Retailer', 'field': 'name', 'align': 'left'},
                {'name': 'queries', 'label': 'Queries', 'field': 'queries', 'align': 'right'},
                {'name': 'avg_cashback', 'label': 'Avg CB', 'field': 'avg_cashback', 'align': 'right'},
            ]
            
            # Use real data or show empty state
            if top_retailers:
                ui.table(columns=columns, rows=top_retailers).classes('w-full').props('dark flat dense')
            else:
                ui.label('No retailer data yet. Run some searches to populate.').classes('text-gray-400 text-sm')
        
        # Platform Status with real data
        with ui.card().classes('w-full glass rounded-xl p-6 mt-6'):
            ui.label('Platform Status').classes('text-lg font-semibold text-white mb-4')
            
            # Default platforms if no data
            if not platform_status:
                platform_status = [
                    {'name': 'Rakuten', 'active': True, 'success_rate': '—'},
                    {'name': 'TopCashback', 'active': True, 'success_rate': '—'},
                    {'name': 'Honey', 'active': True, 'success_rate': '—'},
                    {'name': 'BeFrugal', 'active': True, 'success_rate': '—'},
                    {'name': 'Swagbucks', 'active': True, 'success_rate': '—'},
                ]
            
            for platform in platform_status:
                name = platform.get('name', 'Unknown')
                active = platform.get('active', False)
                rate = platform.get('success_rate_display', platform.get('success_rate', '—'))
                reliable = platform.get('reliable', True)
                
                with ui.row().classes('w-full justify-between items-center py-2 sm:py-3 border-b border-gray-700/30 flex-wrap gap-2'):
                    with ui.row().classes('items-center gap-2 sm:gap-3'):
                        ui.icon('circle', size='xs', color='green' if active else 'red')
                        ui.label(name).classes('text-white text-sm sm:text-base')
                    ui.label('Active' if active else 'Inactive').classes('text-gray-400 text-xs sm:text-sm hidden sm:block')
                    ui.label(rate).classes('text-emerald-400 font-medium text-sm sm:text-base')
        
        # Users section (from database)
        with ui.card().classes('w-full glass rounded-xl p-4 sm:p-6 mt-4 sm:mt-6'):
            ui.label('Users').classes('text-base sm:text-lg font-semibold text-white mb-4')
            
            all_users = state.db.get_all_users()
            if not all_users:
                ui.label('No users yet.').classes('text-gray-400 text-sm')
            else:
                for u in all_users:
                    with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-700/30 flex-wrap gap-2'):
                        ui.label(u.email).classes('text-white text-sm sm:text-base break-all')
                        ui.badge('Admin' if u.is_admin else 'User').props(f'color={"positive" if u.is_admin else "gray"}')
                        ui.label(u.created_at[:10] if u.created_at else '').classes('text-gray-500 text-xs sm:text-sm hidden sm:block')

def create_cards():
    """Create cards page with database persistence."""
    # Redirect if not authenticated
    if not is_authenticated():
        ui.navigate.to('/login')
        return
    
    user_id = get_current_user_id()
    if not user_id:
        ui.navigate.to('/login')
        return
    
    cards_container = None
    
    def render_wallet():
        """Render the wallet cards list from database."""
        nonlocal cards_container
        if cards_container:
            cards_container.clear()
        
        with cards_container:
            user_cards = state.db.get_user_cards(user_id)
            if not user_cards:
                with ui.column().classes('items-center py-6 sm:py-8'):
                    ui.icon('credit_card_off', size='xl', color='gray')
                    ui.label('No cards added').classes('text-gray-400 mt-4')
            else:
                for card in user_cards:
                    with ui.row().classes('w-full justify-between items-center p-3 sm:p-4 bg-gray-800/50 rounded-lg mb-2 flex-wrap gap-2'):
                        with ui.column():
                            ui.label(card.name).classes('text-white font-medium text-sm sm:text-base')
                            ui.label(f'{card.issuer} · {card.base_rate}% base').classes('text-gray-400 text-xs sm:text-sm')
                        
                        def remove_card(card_id=card.card_id, card_name=card.name):
                            state.db.remove_card_from_wallet(user_id, card_id)
                            ui.notify(f'Removed {card_name}', type='info')
                            render_wallet()
                        
                        ui.button(icon='close', on_click=remove_card).props('flat round size=sm color=gray')
    
    with ui.column().classes('w-full max-w-4xl mx-auto px-4 sm:px-6 py-6 sm:py-8'):
        ui.button('← Back', on_click=lambda: ui.navigate.to('/')).props('flat color=gray size=sm')
        
        ui.label('My Cards').classes('text-2xl sm:text-3xl font-bold text-white mt-4 mb-6 sm:mb-8')
        
        with ui.card().classes('w-full glass rounded-xl p-4 sm:p-6'):
            ui.label('Your Wallet').classes('text-base sm:text-lg font-semibold text-white mb-4')
            cards_container = ui.column().classes('w-full')
            render_wallet()
        
        with ui.card().classes('w-full glass rounded-xl p-4 sm:p-6 mt-4 sm:mt-6'):
            ui.label('Add Cards').classes('text-base sm:text-lg font-semibold text-white mb-4')
            
            # Popular cards to choose from (use card_id as key)
            available_cards = [
                {"card_id": "chase_sapphire_preferred", "name": "Chase Sapphire Preferred", "issuer": "Chase", "base_rate": 1.0, "highlights": ["3x Dining", "3x Travel"]},
                {"card_id": "amex_gold", "name": "Amex Gold", "issuer": "Amex", "base_rate": 1.0, "highlights": ["4x Dining", "4x Groceries"]},
                {"card_id": "citi_double_cash", "name": "Citi Double Cash", "issuer": "Citi", "base_rate": 2.0, "highlights": ["2% Everything"]},
                {"card_id": "chase_freedom_flex", "name": "Chase Freedom Flex", "issuer": "Chase", "base_rate": 1.0, "highlights": ["5x Rotating", "3x Dining"]},
                {"card_id": "discover_it", "name": "Discover it", "issuer": "Discover", "base_rate": 1.0, "highlights": ["5x Rotating"]},
                {"card_id": "amazon_prime_visa", "name": "Amazon Prime Visa", "issuer": "Chase", "base_rate": 1.0, "highlights": ["5x Amazon", "2x Dining"]},
            ]
            
            with ui.element('div').classes('grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4'):
                for c in available_cards:
                    with ui.card().classes('bg-gray-800/50 hover:bg-gray-700/50 transition p-4 rounded-xl cursor-pointer'):
                        ui.label(c["name"]).classes('text-white font-medium text-sm')
                        ui.label(c["issuer"]).classes('text-gray-400 text-xs')
                        ui.label(' · '.join(c["highlights"])).classes('text-emerald-400 text-xs mt-2')
                        
                        def add_card(card=c):
                            result = state.db.add_card_to_wallet(
                                user_id=user_id,
                                card_id=card["card_id"],
                                name=card["name"],
                                issuer=card["issuer"],
                                base_rate=card["base_rate"],
                                is_custom=False
                            )
                            if result:
                                ui.notify(f'Added {card["name"]}', type='positive')
                                render_wallet()
                            else:
                                ui.notify(f'{card["name"]} already in wallet', type='info')
                        
                        ui.button('Add', on_click=add_card).props('flat color=primary size=sm').classes('mt-3')

def create_settings():
    """Create settings page with database persistence."""
    # Redirect if not authenticated
    if not is_authenticated():
        ui.navigate.to('/login')
        return
    
    user = get_current_user()
    if not user:
        ui.navigate.to('/login')
        return
    
    # US States with tax rates
    states = [
        "Alabama", "Alaska", "Arizona", "Arkansas", "California",
        "Colorado", "Connecticut", "Delaware", "Florida", "Georgia",
        "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
        "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
        "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri",
        "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
        "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
        "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
        "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
        "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming"
    ]
    
    def on_location_change(e):
        state.db.update_user_settings(user.id, location=e.value)
        ui.notify(f'Location set to {e.value}', type='positive')
    
    def on_tax_change(e):
        try:
            tax_rate = float(e.value) if e.value else None
            state.db.update_user_settings(user.id, tax_rate=tax_rate)
            ui.notify(f'Tax rate saved', type='positive')
        except ValueError:
            ui.notify('Invalid tax rate', type='warning')
    
    with ui.column().classes('w-full max-w-xl mx-auto px-4 sm:px-6 py-6 sm:py-8'):
        ui.button('← Back', on_click=lambda: ui.navigate.to('/')).props('flat color=gray size=sm')
        
        ui.label('Settings').classes('text-2xl sm:text-3xl font-bold text-white mt-4 mb-6 sm:mb-8')
        
        # Account info
        with ui.card().classes('w-full glass rounded-xl p-4 sm:p-6 mb-4'):
            ui.label('Account').classes('text-base sm:text-lg font-semibold text-white mb-4')
            ui.label(f'Email: {user.email}').classes('text-gray-300')
            ui.label(f'Member since: {user.created_at[:10] if user.created_at else "N/A"}').classes('text-gray-400 text-sm')
        
        # Location settings
        with ui.card().classes('w-full glass rounded-xl p-4 sm:p-6 mb-4'):
            ui.label('Location').classes('text-base sm:text-lg font-semibold text-white mb-4')
            ui.label('Your location helps us calculate accurate sales tax.').classes('text-gray-400 text-sm mb-4')
            
            ui.select(
                states, 
                label='State', 
                value=user.location,
                on_change=on_location_change
            ).classes('w-full')
        
        # Tax settings
        with ui.card().classes('w-full glass rounded-xl p-4 sm:p-6'):
            ui.label('Tax Rate Override').classes('text-base sm:text-lg font-semibold text-white mb-4')
            ui.label('Leave blank to use automatic detection based on location.').classes('text-gray-400 text-sm mb-4')
            
            ui.input(
                'Custom Tax Rate (%)',
                value=str(user.tax_rate) if user.tax_rate else '',
                on_change=on_tax_change
            ).props('type=number step=0.01 min=0 max=15').classes('w-full')
        
        # Savings stats
        stats = state.db.get_user_savings_stats(user.id)
        if stats['total_searches'] > 0:
            with ui.card().classes('w-full glass rounded-xl p-4 sm:p-6 mt-4'):
                ui.label('Your Savings').classes('text-base sm:text-lg font-semibold text-white mb-4')
                with ui.row().classes('gap-6'):
                    with ui.column():
                        ui.label(f'{stats["total_searches"]}').classes('text-2xl font-bold text-emerald-400')
                        ui.label('Searches').classes('text-gray-400 text-sm')
                    with ui.column():
                        ui.label(f'${stats["total_saved"]:.2f}').classes('text-2xl font-bold text-emerald-400')
                        ui.label('Total Saved').classes('text-gray-400 text-sm')

def create_footer():
    """Create footer."""
    with ui.element('footer').classes('w-full bg-gray-900/50 border-t border-gray-800/50 mt-auto'):
        with ui.row().classes('w-full max-w-6xl mx-auto px-4 sm:px-6 py-4 sm:py-6 justify-center sm:justify-between items-center'):
            ui.label('© 2026 NetPrice').classes('text-gray-500 text-xs sm:text-sm')

# =============================================================================
# Pages
# =============================================================================

@ui.page('/')
async def main_page():
    ui.add_head_html(CUSTOM_CSS)
    ui.dark_mode().enable()
    
    create_navbar()
    with ui.column().classes('w-full min-h-screen bg-gray-900 pt-16'):
        if is_authenticated():
            create_hero_search()
        else:
            create_landing()
        create_footer()

@ui.page('/results')
async def results_page():
    ui.add_head_html(CUSTOM_CSS)
    ui.dark_mode().enable()
    
    create_navbar()
    with ui.column().classes('w-full min-h-screen bg-gray-900 pt-16'):
        create_results()
        create_footer()

@ui.page('/login')
async def login_page():
    ui.add_head_html(CUSTOM_CSS)
    ui.dark_mode().enable()
    
    create_navbar()
    with ui.column().classes('w-full min-h-screen bg-gray-900 pt-16'):
        create_login()
        create_footer()

@ui.page('/register')
async def register_page():
    ui.add_head_html(CUSTOM_CSS)
    ui.dark_mode().enable()
    
    create_navbar()
    with ui.column().classes('w-full min-h-screen bg-gray-900 pt-16'):
        create_register()
        create_footer()

@ui.page('/admin')
async def admin_page():
    ui.add_head_html(CUSTOM_CSS)
    ui.dark_mode().enable()
    
    create_navbar()
    with ui.column().classes('w-full min-h-screen bg-gray-900 pt-16'):
        await create_admin()
        create_footer()

@ui.page('/cards')
async def cards_page():
    ui.add_head_html(CUSTOM_CSS)
    ui.dark_mode().enable()
    
    create_navbar()
    with ui.column().classes('w-full min-h-screen bg-gray-900 pt-16'):
        create_cards()
        create_footer()

@ui.page('/settings')
async def settings_page():
    ui.add_head_html(CUSTOM_CSS)
    ui.dark_mode().enable()
    
    create_navbar()
    with ui.column().classes('w-full min-h-screen bg-gray-900 pt-16'):
        create_settings()
        create_footer()

@ui.page('/health')
async def health():
    return {'status': 'healthy', 'version': '0.6.0'}

# =============================================================================
# Main
# =============================================================================

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        host='0.0.0.0',
        port=8080,
        title='NetPrice Finder',
        favicon='💰',
        reload=False,
        show=False,
        storage_secret=STORAGE_SECRET
    )
