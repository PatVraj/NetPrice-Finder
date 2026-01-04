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

# =============================================================================
# Configuration
# =============================================================================

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
API_URL = os.getenv("API_URL", "http://localhost:8000")

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
    user_cards: List[UserCard] = []
    user_tax_rate: Optional[float] = None
    user_location: Optional[str] = None
    users_db: Dict[str, User] = {}

state = AppState()

# Demo admin user
state.users_db["admin@netprice.local"] = User(
    id="1",
    email="admin@netprice.local",
    password_hash=hashlib.sha256("admin123".encode()).hexdigest(),
    is_admin=True,
    created_at=datetime.now().isoformat()
)

# =============================================================================
# Authentication Helpers
# =============================================================================

def hash_password(password: str) -> str:
    """Hash a password."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(password) == password_hash

def get_current_user() -> Optional[User]:
    """Get the currently logged in user."""
    user_email = app.storage.user.get('email')
    if user_email and user_email in state.users_db:
        return state.users_db[user_email]
    return None

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
    """Initialize Redis connection."""
    try:
        client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=False)
        await client.ping()
        return client
    except Exception as e:
        print(f"⚠️ Redis connection failed: {e}")
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
            response = await client.get(f"{API_URL}/intelligence/stats")
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass
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
    
    .glass {
        background: rgba(31, 41, 55, 0.8);
        backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.08);
    }
    
    .hero-bg {
        background: linear-gradient(135deg, #064e3b 0%, #0f172a 50%, #1e1b4b 100%);
    }
    
    .glow {
        text-shadow: 0 0 30px rgba(16, 185, 129, 0.4);
    }
    
    .stat-card {
        background: linear-gradient(145deg, #1f2937 0%, #111827 100%);
        border: 1px solid rgba(255, 255, 255, 0.05);
    }
    
    .fade-in {
        animation: fadeIn 0.4s ease-out;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .search-box {
        background: rgba(17, 24, 39, 0.9) !important;
        border: 2px solid rgba(16, 185, 129, 0.2) !important;
        transition: border-color 0.2s !important;
    }
    
    .search-box:focus-within {
        border-color: #10b981 !important;
    }
</style>
"""

# =============================================================================
# UI Components
# =============================================================================

def create_navbar():
    """Create the navigation bar."""
    with ui.header().classes('bg-gray-900/95 backdrop-blur-md border-b border-gray-800/50'):
        with ui.row().classes('w-full max-w-6xl mx-auto px-6 py-3 items-center justify-between'):
            with ui.link('/', target='_self').classes('no-underline'):
                with ui.row().classes('items-center gap-2'):
                    ui.html('<span class="text-2xl">💰</span>', sanitize=False)
                    ui.label('NetPrice').classes('text-xl font-bold text-white tracking-tight')
            
            with ui.row().classes('items-center gap-4'):
                if is_authenticated():
                    user = get_current_user()
                    ui.link('Search', '/').classes('text-gray-400 hover:text-white transition-colors no-underline text-sm')
                    ui.link('Cards', '/cards').classes('text-gray-400 hover:text-white transition-colors no-underline text-sm')
                    
                    if is_admin():
                        ui.link('Admin', '/admin').classes('text-emerald-400 hover:text-emerald-300 transition-colors no-underline text-sm font-medium')
                    
                    with ui.button(icon='account_circle').props('flat round size=sm color=gray'):
                        with ui.menu().classes('bg-gray-800'):
                            ui.menu_item(f'{user.email}').props('disable').classes('text-gray-400')
                            ui.separator()
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
    with ui.element('div').classes('w-full hero-bg min-h-[70vh] flex items-center'):
        with ui.column().classes('w-full max-w-3xl mx-auto px-6 py-20 items-center'):
            ui.html('<h1 class="text-5xl md:text-6xl font-bold text-white text-center mb-4 glow tracking-tight">Your True Price</h1>', sanitize=False)
            ui.label('Compare cashback across 5 platforms instantly').classes(
                'text-xl text-gray-400 text-center mb-12'
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
            
            with ui.row().classes('mt-20 gap-12 flex-wrap justify-center'):
                for icon, val, lbl in [('💵', '5', 'Cashback Sites'), ('💳', '50+', 'Cards Supported'), ('⚡', '<3s', 'Analysis Time')]:
                    with ui.column().classes('items-center'):
                        ui.html(f'<span class="text-2xl">{icon}</span>', sanitize=False)
                        ui.label(val).classes('text-xl font-bold text-white mt-2')
                        ui.label(lbl).classes('text-gray-500 text-sm')
            
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
    with ui.element('div').classes('w-full hero-bg min-h-[85vh] flex items-center justify-center'):
        with ui.column().classes('items-center px-6'):
            ui.html('<span class="text-6xl mb-6">💰</span>', sanitize=False)
            ui.html('<h1 class="text-5xl md:text-6xl font-bold text-white text-center mb-4 glow tracking-tight">NetPrice Finder</h1>', sanitize=False)
            ui.label('Find the TRUE cheapest price after all savings').classes('text-xl text-gray-400 text-center mb-10 max-w-lg')
            
            with ui.row().classes('gap-4'):
                ui.button('Get Started', on_click=lambda: ui.navigate.to('/register')).props('color=primary size=lg unelevated')
                ui.button('Login', on_click=lambda: ui.navigate.to('/login')).props('flat text-color=white size=lg')

def create_results():
    """Create results display."""
    if not state.current_result:
        ui.navigate.to('/')
        return
    
    r = state.current_result
    
    with ui.column().classes('w-full max-w-2xl mx-auto px-6 py-8 fade-in'):
        ui.button('← Back', on_click=lambda: ui.navigate.to('/')).props('flat color=gray size=sm')
        
        with ui.card().classes('w-full glass rounded-2xl p-6 mt-4'):
            ui.label(r.retailer.upper()).classes('text-emerald-400 text-xs font-semibold tracking-widest')
            ui.label(r.product_name or 'Product').classes('text-xl font-bold text-white mt-1')
            ui.label(f'${r.product_price:.2f}').classes('text-2xl font-bold text-gray-500 mt-2')
        
        with ui.card().classes('w-full glass rounded-2xl p-6 mt-4'):
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
    with ui.column().classes('w-full max-w-sm mx-auto px-6 py-20 items-center'):
        ui.label('Welcome back').classes('text-3xl font-bold text-white mb-2')
        ui.label('Sign in to continue').classes('text-gray-400 mb-8')
        
        with ui.card().classes('w-full glass rounded-2xl p-8'):
            email = ui.input('Email').classes('w-full mb-4')
            password = ui.input('Password', password=True, password_toggle_button=True).classes('w-full mb-6')
            
            btn = ui.button('Sign In').props('color=primary unelevated').classes('w-full')
            
            async def login():
                e, p = email.value.strip(), password.value
                if not e or not p:
                    ui.notify('Fill in all fields', type='warning')
                    return
                user = state.users_db.get(e)
                if user and verify_password(p, user.password_hash):
                    app.storage.user['authenticated'] = True
                    app.storage.user['email'] = e
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
    with ui.column().classes('w-full max-w-sm mx-auto px-6 py-20 items-center'):
        ui.label('Create account').classes('text-3xl font-bold text-white mb-2')
        ui.label('Start saving today').classes('text-gray-400 mb-8')
        
        with ui.card().classes('w-full glass rounded-2xl p-8'):
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
                if e in state.users_db:
                    ui.notify('Email already registered', type='warning')
                    return
                
                state.users_db[e] = User(
                    id=secrets.token_hex(8),
                    email=e,
                    password_hash=hash_password(p),
                    is_admin=False,
                    created_at=datetime.now().isoformat()
                )
                app.storage.user['authenticated'] = True
                app.storage.user['email'] = e
                ui.notify('Account created!', type='positive')
                ui.navigate.to('/')
            
            btn.on('click', register)
        
        with ui.row().classes('mt-6 gap-2'):
            ui.label("Have an account?").classes('text-gray-400 text-sm')
            ui.link('Sign in', '/login').classes('text-emerald-400 text-sm no-underline')

def create_admin():
    """Create admin dashboard."""
    if not is_admin():
        ui.navigate.to('/')
        return
    
    with ui.column().classes('w-full max-w-6xl mx-auto px-6 py-8'):
        ui.label('Admin Dashboard').classes('text-3xl font-bold text-white mb-8')
        
        with ui.row().classes('w-full gap-4 mb-8 flex-wrap'):
            for label, value, icon, color in [
                ('Retailers', '156', 'store', 'emerald'),
                ('Cashback Entries', '423', 'attach_money', 'blue'),
                ('Total Queries', '1,847', 'search', 'purple'),
                ('Users', str(len(state.users_db)), 'people', 'amber'),
            ]:
                with ui.card().classes('flex-1 min-w-[200px] stat-card rounded-xl p-5'):
                    with ui.row().classes('items-center gap-4'):
                        ui.icon(icon, size='md', color=color)
                        with ui.column().classes('gap-0'):
                            ui.label(value).classes('text-2xl font-bold text-white')
                            ui.label(label).classes('text-gray-400 text-xs')
        
        with ui.card().classes('w-full glass rounded-xl p-6'):
            ui.label('Top Retailers').classes('text-lg font-semibold text-white mb-4')
            
            columns = [
                {'name': 'rank', 'label': '#', 'field': 'rank', 'align': 'left'},
                {'name': 'name', 'label': 'Retailer', 'field': 'name', 'align': 'left'},
                {'name': 'queries', 'label': 'Queries', 'field': 'queries', 'align': 'right'},
                {'name': 'avg_cashback', 'label': 'Avg CB', 'field': 'avg_cashback', 'align': 'right'},
            ]
            
            rows = [
                {'rank': 1, 'name': 'Amazon', 'queries': 542, 'avg_cashback': '4.2%'},
                {'rank': 2, 'name': 'Target', 'queries': 234, 'avg_cashback': '2.5%'},
                {'rank': 3, 'name': 'Walmart', 'queries': 198, 'avg_cashback': '3.1%'},
                {'rank': 4, 'name': 'Best Buy', 'queries': 156, 'avg_cashback': '5.0%'},
                {'rank': 5, 'name': 'Nike', 'queries': 89, 'avg_cashback': '8.0%'},
            ]
            
            ui.table(columns=columns, rows=rows).classes('w-full').props('dark flat dense')
        
        with ui.card().classes('w-full glass rounded-xl p-6 mt-6'):
            ui.label('Platform Status').classes('text-lg font-semibold text-white mb-4')
            
            platforms = [
                ('Rakuten', True, '98%'),
                ('TopCashback', True, '95%'),
                ('Honey', False, '—'),
                ('BeFrugal', True, '92%'),
                ('Swagbucks', True, '89%'),
            ]
            
            for name, active, rate in platforms:
                with ui.row().classes('w-full justify-between items-center py-3 border-b border-gray-700/30'):
                    with ui.row().classes('items-center gap-3'):
                        ui.icon('circle', size='xs', color='green' if active else 'red')
                        ui.label(name).classes('text-white')
                    ui.label('Active' if active else 'Disabled').classes('text-gray-400 text-sm')
                    ui.label(rate).classes('text-emerald-400 font-medium')
        
        with ui.card().classes('w-full glass rounded-xl p-6 mt-6'):
            ui.label('Users').classes('text-lg font-semibold text-white mb-4')
            
            for u in state.users_db.values():
                with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-700/30'):
                    ui.label(u.email).classes('text-white')
                    ui.badge('Admin' if u.is_admin else 'User').props(f'color={"positive" if u.is_admin else "gray"}')
                    ui.label(u.created_at[:10]).classes('text-gray-500 text-sm')

def create_cards():
    """Create cards page."""
    with ui.column().classes('w-full max-w-4xl mx-auto px-6 py-8'):
        ui.button('← Back', on_click=lambda: ui.navigate.to('/')).props('flat color=gray size=sm')
        
        ui.label('My Cards').classes('text-3xl font-bold text-white mt-4 mb-8')
        
        with ui.card().classes('w-full glass rounded-xl p-6'):
            ui.label('Your Wallet').classes('text-lg font-semibold text-white mb-4')
            
            if not state.user_cards:
                with ui.column().classes('items-center py-8'):
                    ui.icon('credit_card_off', size='xl', color='gray')
                    ui.label('No cards added').classes('text-gray-400 mt-4')
            else:
                for card in state.user_cards:
                    with ui.row().classes('w-full justify-between items-center p-4 bg-gray-800/50 rounded-lg mb-2'):
                        with ui.column():
                            ui.label(card.name).classes('text-white font-medium')
                            ui.label(card.issuer).classes('text-gray-400 text-sm')
                        ui.button(icon='close').props('flat round size=sm color=gray')
        
        with ui.card().classes('w-full glass rounded-xl p-6 mt-6'):
            ui.label('Add Cards').classes('text-lg font-semibold text-white mb-4')
            
            cards = [
                UserCard("Chase Sapphire Preferred", "Chase", 1.0, ["3x Dining", "3x Travel"]),
                UserCard("Amex Gold", "Amex", 1.0, ["4x Dining", "4x Groceries"]),
                UserCard("Citi Double Cash", "Citi", 2.0, ["2% Everything"]),
            ]
            
            with ui.row().classes('gap-4 flex-wrap'):
                for c in cards:
                    with ui.card().classes('w-56 bg-gray-800/50 hover:bg-gray-700/50 transition p-4 rounded-xl cursor-pointer'):
                        ui.label(c.name).classes('text-white font-medium text-sm')
                        ui.label(c.issuer).classes('text-gray-400 text-xs')
                        ui.label(' · '.join(c.highlights)).classes('text-emerald-400 text-xs mt-2')
                        
                        async def add(card=c):
                            state.user_cards.append(card)
                            ui.notify(f'Added {card.name}', type='positive')
                        
                        ui.button('Add', on_click=add).props('flat color=primary size=sm').classes('mt-3')

def create_settings():
    """Create settings page."""
    with ui.column().classes('w-full max-w-xl mx-auto px-6 py-8'):
        ui.button('← Back', on_click=lambda: ui.navigate.to('/')).props('flat color=gray size=sm')
        
        ui.label('Settings').classes('text-3xl font-bold text-white mt-4 mb-8')
        
        with ui.card().classes('w-full glass rounded-xl p-6'):
            ui.label('Location').classes('text-lg font-semibold text-white mb-4')
            
            states = ["California", "Texas", "New York", "Florida", "Oregon"]
            ui.select(states, label='State', value=state.user_location).classes('w-full')

def create_footer():
    """Create footer."""
    with ui.element('footer').classes('w-full bg-gray-900/50 border-t border-gray-800/50 mt-auto'):
        with ui.row().classes('w-full max-w-6xl mx-auto px-6 py-6 justify-between items-center'):
            ui.label('© 2026 NetPrice').classes('text-gray-500 text-sm')

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
        create_admin()
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
        storage_secret='netprice-secret-key-change-in-production'
    )
