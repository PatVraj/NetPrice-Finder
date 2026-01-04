"""
Net Price Finder - Frontend Application
NiceGUI Dashboard for finding the TRUE cheapest price

Paste a product link → Get the real net price after all savings stack:
- Cashback (Rakuten, TopCashback, Honey, etc.)
- Coupons (auto-discovered)
- Credit card rewards (optional, only YOUR cards)
"""

import os
from nicegui import ui, app
import httpx
import redis.asyncio as redis
import asyncio
from contextlib import asynccontextmanager
import base64
from typing import Optional, List
import json
from dataclasses import dataclass, field
from datetime import datetime

# =============================================================================
# Configuration
# =============================================================================

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://ollama:11434")
SCRAPER_API_URL = os.getenv("SCRAPER_API_URL", "http://scraper-engine:5000")
API_URL = os.getenv("API_URL", "http://localhost:8000")
FIREFLY_API_URL = os.getenv("FIREFLY_API_URL", "http://firefly:8080")

# =============================================================================
# Application State
# =============================================================================

@dataclass
class PromoCodeResult:
    """A promo code found from cashback platforms."""
    code: str
    source: str
    description: Optional[str] = None
    discount_percent: Optional[float] = None
    discount_amount: Optional[float] = None

@dataclass
class CashbackSearchResult:
    """Result from checking a single cashback platform."""
    platform: str
    rate: float = 0.0
    found: bool = False
    error: Optional[str] = None

@dataclass
class PromoSearchResult:
    """Result from checking a promo code source."""
    source: str
    codes_found: int = 0
    error: Optional[str] = None

@dataclass
class SearchTransparency:
    """Transparency into what was searched and found."""
    cashback_platforms_checked: List[CashbackSearchResult] = field(default_factory=list)
    promo_sources_checked: List[PromoSearchResult] = field(default_factory=list)
    tax_source: str = "default"  # "browser", "ip", "default"
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
    available_promo_codes: List[PromoCodeResult] = field(default_factory=list)
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

class AppState:
    """Global application state."""
    redis_client: Optional[redis.Redis] = None
    scraper_frame: str = ""
    is_scraping: bool = False
    is_loading: bool = False
    command_history: list = []
    current_result: Optional[PriceResult] = None
    user_cards: List[UserCard] = []
    popular_cards: List[UserCard] = []
    # User's tax settings (from browser or manual entry)
    user_tax_rate: Optional[float] = None  # Tax rate in percentage
    user_location: Optional[str] = None    # State/city name

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
# API Client
# =============================================================================

async def find_best_price(query: str) -> Optional[PriceResult]:
    """Call the optimizer API to find best price."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:  # 2 minute timeout for scraping
            # Build request with user's tax settings if available
            request_data = {
                "query": query, 
                "include_cashback": True, 
                "include_coupons": True
            }
            if state.user_tax_rate is not None:
                request_data["user_tax_rate"] = state.user_tax_rate
                request_data["user_location"] = state.user_location
            
            response = await client.post(
                f"{API_URL}/api/v1/find-best-price",
                json=request_data
            )
            if response.status_code == 200:
                data = response.json()
                
                # Parse promo codes
                promo_codes = []
                for p in data.get("available_promo_codes", []):
                    promo_codes.append(PromoCodeResult(
                        code=p.get("code", ""),
                        source=p.get("source", ""),
                        description=p.get("description"),
                        discount_percent=p.get("discount_percent"),
                        discount_amount=p.get("discount_amount"),
                    ))
                
                # Parse search transparency
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
                    promo_results = [
                        PromoSearchResult(
                            source=p.get("source", ""),
                            codes_found=p.get("codes_found", 0),
                            error=p.get("error")
                        )
                        for p in t.get("promo_sources_checked", [])
                    ]
                    transparency = SearchTransparency(
                        cashback_platforms_checked=cashback_results,
                        promo_sources_checked=promo_results,
                        tax_source=t.get("tax_source", "default"),
                        search_duration_ms=t.get("search_duration_ms", 0)
                    )
                
                # Build PriceResult, excluding timestamp and handling complex objects
                result_data = {k: v for k, v in data.items() 
                              if k not in ['timestamp', 'available_promo_codes', 'search_transparency']}
                result_data['available_promo_codes'] = promo_codes
                result_data['search_transparency'] = transparency
                
                return PriceResult(**result_data)
            return None
    except Exception as e:
        print(f"API Error: {e}")
        return None

async def quick_calculate(
    product_price: float,
    cashback_percent: float = 0,
    card_reward_percent: float = 0,
    coupon_discount: float = 0,
    tax_rate: float = 0.0825,
    shipping: float = 0
) -> dict:
    """Quick price calculation without scraping."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{API_URL}/api/v1/quick-price",
                json={
                    "product_price": product_price,
                    "cashback_percent": cashback_percent,
                    "card_reward_percent": card_reward_percent,
                    "coupon_discount": coupon_discount,
                    "tax_rate": tax_rate,
                    "shipping": shipping
                }
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        print(f"Quick calc error: {e}")
    
    # Fallback to local calculation
    gross = product_price - coupon_discount + (product_price * tax_rate) + shipping
    cashback = gross * (cashback_percent / 100)
    card_rewards = gross * (card_reward_percent / 100)
    net = gross - cashback - card_rewards
    total_savings = product_price - net + coupon_discount
    
    return {
        "product_price": product_price,
        "coupon_discount": coupon_discount,
        "tax": product_price * tax_rate,
        "shipping": shipping,
        "gross_total": gross,
        "cashback": cashback,
        "card_rewards": card_rewards,
        "net_price": net,
        "total_savings": total_savings,
        "savings_percent": (total_savings / product_price * 100) if product_price > 0 else 0
    }

async def get_user_wallet() -> List[UserCard]:
    """Get user's card wallet from API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{API_URL}/api/v1/wallet")
            if response.status_code == 200:
                data = response.json()
                return [
                    UserCard(
                        name=c["name"],
                        issuer=c["issuer"],
                        base_rate=c["base_rate"],
                        highlights=[f"{bc['rate']}x {bc['category']}" for bc in c.get("bonus_categories", [])]
                    )
                    for c in data.get("cards", [])
                ]
    except Exception:
        pass
    return []

async def get_popular_cards() -> List[UserCard]:
    """Get list of popular cards from API."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{API_URL}/api/v1/popular-cards")
            if response.status_code == 200:
                data = response.json()
                return [
                    UserCard(
                        name=c["name"],
                        issuer=c["issuer"],
                        base_rate=c["base_rate"],
                        highlights=c.get("highlights", [])
                    )
                    for c in data.get("cards", [])
                ]
    except Exception:
        pass
    return []

async def add_card_to_wallet(card_name: str) -> bool:
    """Add a popular card to user's wallet."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{API_URL}/api/v1/wallet/add-popular/{card_name}")
            return response.status_code == 200
    except Exception:
        return False

async def remove_card_from_wallet(card_name: str) -> bool:
    """Remove a card from user's wallet."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(f"{API_URL}/api/v1/wallet/{card_name}")
            return response.status_code == 200
    except Exception:
        return False

# =============================================================================
# UI Components
# =============================================================================

def create_header():
    """Create the application header."""
    with ui.header().classes('bg-gradient-to-r from-emerald-800 to-teal-900'):
        with ui.row().classes('w-full items-center px-4'):
            ui.link('💰 Net Price Finder', '/').classes('text-2xl font-bold text-white no-underline')
            ui.label('Find the TRUE cheapest price').classes('text-emerald-200 ml-4 text-sm')
            ui.space()
            with ui.row().classes('gap-4'):
                ui.button('My Cards', on_click=lambda: ui.navigate.to('/cards'), icon='credit_card').props('flat text-color=white')
                ui.button('Settings', on_click=lambda: ui.navigate.to('/settings'), icon='settings').props('flat text-color=white')

def create_search_hero():
    """Create the main search hero section."""
    with ui.card().classes('w-full bg-gradient-to-br from-gray-800 to-gray-900 border-none'):
        with ui.column().classes('w-full items-center py-8 px-4'):
            ui.label('🔍 Paste a product link').classes('text-3xl font-bold text-white mb-2')
            ui.label('We\'ll find cashback, coupons, and the best card to use').classes('text-gray-400 mb-6')
            
            with ui.row().classes('w-full max-w-3xl gap-2'):
                search_input = ui.input(
                    placeholder='https://amazon.com/dp/... or "Nike Air Max 90"'
                ).classes('flex-grow text-lg').props('outlined dark dense bg-color=grey-9')
                
                search_button = ui.button('Find Best Price', icon='search').props('color=positive size=lg')
                
            # Loading indicator
            loading_spinner = ui.spinner('dots', size='lg', color='positive').classes('mt-4')
            loading_spinner.visible = False
            
            # Progress log area
            progress_container = ui.column().classes('w-full max-w-3xl mt-4')
            progress_container.visible = False
            
            with progress_container:
                progress_log = ui.log(max_lines=10).classes(
                    'w-full h-32 bg-gray-900 text-green-400 font-mono text-sm rounded border border-gray-700'
                )
            
            async def update_progress(message: str):
                """Add a message to the progress log."""
                from datetime import datetime
                timestamp = datetime.now().strftime("%H:%M:%S")
                progress_log.push(f"[{timestamp}] {message}")
            
            async def do_search():
                query = search_input.value.strip()
                if not query:
                    ui.notify('Please enter a product URL or search term', type='warning')
                    return
                
                loading_spinner.visible = True
                progress_container.visible = True
                progress_log.clear()
                state.is_loading = True
                search_button.disable()
                
                try:
                    if query.startswith('http'):
                        await update_progress(f"🔗 Analyzing URL: {query[:60]}...")
                        await update_progress("🌐 Connecting to scraper engine...")
                        await asyncio.sleep(0.1)  # Let UI update
                        
                        await update_progress("📄 Loading page content...")
                        await asyncio.sleep(0.1)
                        
                        # Call the real API
                        result = await find_best_price(query)
                        
                        if result:
                            await update_progress("✅ Product info extracted!")
                            await update_progress(f"💰 Found price: ${result.product_price:.2f}")
                            if result.cashback_percent > 0:
                                await update_progress(f"💵 Cashback available: {result.cashback_percent}%")
                            if result.coupon_code:
                                await update_progress(f"🏷️ Coupon found: {result.coupon_code}")
                            if result.available_promo_codes:
                                await update_progress(f"🎫 Found {len(result.available_promo_codes)} promo codes!")
                            await update_progress("🎯 Calculating best net price...")
                            await asyncio.sleep(0.3)
                            
                            state.current_result = result
                            ui.navigate.to('/results')
                        else:
                            await update_progress("❌ Could not parse product information")
                            await update_progress("💡 Try a different URL or check if the site is supported")
                            ui.notify('Could not analyze this product. The scraper may not support this site yet.', type='warning')
                    else:
                        await update_progress(f"🔍 Searching for: {query}")
                        ui.notify('Product search coming soon! Try pasting a direct URL.', type='info')
                        progress_container.visible = False
                        
                except Exception as e:
                    await update_progress(f"❌ Error: {str(e)}")
                    ui.notify(f'Error: {str(e)}', type='negative')
                finally:
                    loading_spinner.visible = False
                    state.is_loading = False
                    search_button.enable()
            
            search_button.on('click', do_search)
            
            # Quick tips
            with ui.row().classes('mt-8 gap-4 flex-wrap justify-center'):
                with ui.card().classes('bg-gray-800 border-gray-700 px-4 py-2'):
                    ui.label('💳 Add your cards for extra savings').classes('text-sm text-gray-300')
                with ui.card().classes('bg-gray-800 border-gray-700 px-4 py-2'):
                    ui.label('🏷️ We find coupons automatically').classes('text-sm text-gray-300')
                with ui.card().classes('bg-gray-800 border-gray-700 px-4 py-2'):
                    ui.label('💵 Compare 5+ cashback sites').classes('text-sm text-gray-300')

def create_quick_calculator():
    """Create quick price calculator widget."""
    with ui.card().classes('w-full'):
        ui.label('🧮 Quick Calculator').classes('text-lg font-semibold mb-4')
        
        with ui.row().classes('w-full gap-4 flex-wrap'):
            price_input = ui.number('Product Price', value=100, min=0, format='%.2f', prefix='$').classes('w-32')
            cashback_input = ui.number('Cashback %', value=5, min=0, max=50, format='%.1f', suffix='%').classes('w-28')
            coupon_input = ui.number('Coupon', value=10, min=0, format='%.2f', prefix='$').classes('w-28')
            card_input = ui.number('Card Reward %', value=0, min=0, max=10, format='%.1f', suffix='%').classes('w-28')
        
        result_label = ui.label('').classes('text-2xl font-bold text-green-400 mt-4')
        savings_label = ui.label('').classes('text-gray-400')
        
        async def calculate():
            result = await quick_calculate(
                product_price=price_input.value or 0,
                cashback_percent=cashback_input.value or 0,
                coupon_discount=coupon_input.value or 0,
                card_reward_percent=card_input.value or 0,
                tax_rate=0.0825
            )
            result_label.text = f"Net Price: ${result['net_price']:.2f}"
            savings_label.text = f"You save ${result['total_savings']:.2f} ({result['savings_percent']:.1f}%)"
        
        ui.button('Calculate', on_click=calculate, icon='calculate').props('color=primary').classes('mt-2')

def create_how_it_works():
    """Create how it works section."""
    with ui.card().classes('w-full'):
        ui.label('🎯 How It Works').classes('text-xl font-bold mb-4')
        
        with ui.row().classes('w-full gap-8 flex-wrap justify-center'):
            # Step 1
            with ui.column().classes('items-center w-48'):
                ui.icon('link', size='xl', color='primary')
                ui.label('1. Paste Link').classes('font-semibold mt-2')
                ui.label('Drop any product URL').classes('text-sm text-gray-400 text-center')
            
            # Step 2
            with ui.column().classes('items-center w-48'):
                ui.icon('search', size='xl', color='primary')
                ui.label('2. We Search').classes('font-semibold mt-2')
                ui.label('Cashback, coupons, prices').classes('text-sm text-gray-400 text-center')
            
            # Step 3
            with ui.column().classes('items-center w-48'):
                ui.icon('credit_card', size='xl', color='primary')
                ui.label('3. Best Card').classes('font-semibold mt-2')
                ui.label('Optimal card from YOUR wallet').classes('text-sm text-gray-400 text-center')
            
            # Step 4
            with ui.column().classes('items-center w-48'):
                ui.icon('savings', size='xl', color='positive')
                ui.label('4. Net Price').classes('font-semibold mt-2')
                ui.label('TRUE cost after all savings').classes('text-sm text-gray-400 text-center')

def create_results_display():
    """Create the results display page content."""
    if not state.current_result:
        ui.label('No results yet. Search for a product first.').classes('text-gray-400')
        ui.button('← Back to Search', on_click=lambda: ui.navigate.to('/')).props('flat')
        return
    
    r = state.current_result
    
    with ui.card().classes('w-full max-w-2xl mx-auto'):
        # Header
        with ui.row().classes('w-full items-center mb-4'):
            ui.button('←', on_click=lambda: ui.navigate.to('/'), icon='arrow_back').props('flat')
            ui.label(f'Results for {r.retailer}').classes('text-xl font-bold')
        
        # Product Name
        if hasattr(r, 'product_name') and r.product_name:
            ui.label(r.product_name).classes('text-lg text-gray-300 mb-4')
        
        # Original Price
        with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-700'):
            ui.label('Product Price').classes('text-gray-400')
            ui.label(f'${r.product_price:.2f}').classes('text-lg')
        
        # Coupon
        if r.coupon_discount > 0:
            with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-700'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('local_offer', color='amber')
                    ui.label(f'Coupon: {r.coupon_code or "Applied"}').classes('text-amber-400')
                ui.label(f'-${r.coupon_discount:.2f}').classes('text-lg text-green-400')
        
        # Tax with location info
        with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-700'):
            with ui.column().classes('gap-0'):
                tax_label = 'Tax'
                if hasattr(r, 'tax_location') and r.tax_location:
                    tax_label = f'Tax ({r.tax_location})'
                if hasattr(r, 'tax_rate') and r.tax_rate > 0:
                    tax_label += f' @ {r.tax_rate:.1f}%'
                ui.label(tax_label).classes('text-gray-400')
            ui.label(f'+${r.tax:.2f}').classes('text-lg text-gray-400')
        
        if r.shipping > 0:
            with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-700'):
                ui.label('Shipping').classes('text-gray-400')
                ui.label(f'+${r.shipping:.2f}').classes('text-lg text-gray-400')
        
        # Subtotal
        with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-700 bg-gray-800 -mx-4 px-4'):
            ui.label('Subtotal').classes('font-semibold')
            ui.label(f'${r.gross_total:.2f}').classes('text-lg font-semibold')
        
        # Cashback
        if r.cashback_platform:
            with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-700'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('attach_money', color='green')
                    ui.label(f'{r.cashback_platform} ({r.cashback_percent}%)').classes('text-green-400')
                ui.label(f'-${r.cashback_value:.2f}').classes('text-lg text-green-400')
        
        # Card Rewards
        if r.card_name:
            with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-700'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('credit_card', color='blue')
                    ui.label(f'{r.card_name} ({r.card_reward_percent}%)').classes('text-blue-400')
                ui.label(f'-${r.card_reward_value:.2f}').classes('text-lg text-green-400')
        else:
            with ui.row().classes('w-full justify-between items-center py-2 border-b border-gray-700'):
                with ui.row().classes('items-center gap-2'):
                    ui.icon('credit_card_off', color='gray')
                    ui.label('No cards configured').classes('text-gray-500')
                ui.button('Add Cards', on_click=lambda: ui.navigate.to('/cards')).props('flat color=primary size=sm')
        
        # Net Price (Final)
        with ui.card().classes('w-full bg-gradient-to-r from-green-900 to-emerald-900 mt-4'):
            with ui.row().classes('w-full justify-between items-center'):
                ui.label('💰 NET PRICE').classes('text-xl font-bold text-white')
                ui.label(f'${r.net_price:.2f}').classes('text-3xl font-bold text-green-400')
            
            with ui.row().classes('w-full justify-end mt-2'):
                ui.label(f'You save ${r.total_savings:.2f} ({r.savings_percent:.1f}%)').classes('text-green-300')
        
        # Action Buttons
        with ui.row().classes('w-full gap-4 mt-6 justify-center'):
            if r.coupon_code:
                async def copy_coupon():
                    await ui.run_javascript(f'navigator.clipboard.writeText("{r.coupon_code}")')
                    ui.notify(f'Coupon "{r.coupon_code}" copied!', type='positive')
                ui.button(f'Copy Coupon: {r.coupon_code}', on_click=copy_coupon, icon='content_copy').props('color=amber')
            
            if r.cashback_platform:
                ui.button(f'Go to {r.cashback_platform}', icon='open_in_new').props('color=positive')
        
        # Available Promo Codes Section
        if hasattr(r, 'available_promo_codes') and r.available_promo_codes:
            with ui.card().classes('w-full mt-4 bg-gray-800'):
                with ui.row().classes('items-center gap-2 mb-4'):
                    ui.icon('sell', color='amber')
                    ui.label(f'🎫 {len(r.available_promo_codes)} Promo Codes Found').classes('text-lg font-semibold text-amber-400')
                
                with ui.column().classes('gap-2 w-full'):
                    for promo in r.available_promo_codes[:5]:  # Show top 5
                        with ui.card().classes('w-full bg-gray-700'):
                            with ui.row().classes('w-full justify-between items-center'):
                                with ui.column().classes('gap-0'):
                                    with ui.row().classes('items-center gap-2'):
                                        ui.label(promo.code).classes('font-mono font-bold text-amber-300')
                                        ui.badge(promo.source).props('color=blue')
                                    if promo.description:
                                        ui.label(promo.description).classes('text-sm text-gray-400')
                                
                                async def copy_promo(code=promo.code):
                                    await ui.run_javascript(f'navigator.clipboard.writeText("{code}")')
                                    ui.notify(f'Code "{code}" copied!', type='positive')
                                ui.button('Copy', on_click=copy_promo, icon='content_copy').props('flat size=sm')
        
        # Search Transparency Section - What we checked
        with ui.expansion('🔍 What We Searched', icon='info').classes('w-full mt-4'):
            with ui.column().classes('w-full gap-4'):
                # Cashback Platforms Checked
                with ui.card().classes('w-full bg-gray-800'):
                    ui.label('💵 Cashback Platforms').classes('font-semibold text-gray-300 mb-2')
                    
                    if r.search_transparency and r.search_transparency.cashback_platforms_checked:
                        with ui.column().classes('gap-1 w-full'):
                            for cb in r.search_transparency.cashback_platforms_checked:
                                with ui.row().classes('w-full justify-between items-center py-1'):
                                    with ui.row().classes('items-center gap-2'):
                                        if cb.found:
                                            ui.icon('check_circle', size='xs', color='green')
                                        else:
                                            ui.icon('cancel', size='xs', color='gray')
                                        ui.label(cb.platform).classes('text-sm')
                                    if cb.found:
                                        ui.badge(f'{cb.rate}%', color='green').props('dense')
                                    else:
                                        ui.label('Not available').classes('text-xs text-gray-500')
                    else:
                        # Default list if no transparency data
                        platforms = ['Rakuten', 'TopCashback', 'Honey', 'BeFrugal', 'Swagbucks']
                        with ui.column().classes('gap-1 w-full'):
                            for platform in platforms:
                                with ui.row().classes('w-full justify-between items-center py-1'):
                                    with ui.row().classes('items-center gap-2'):
                                        if r.cashback_platform and platform.lower() in r.cashback_platform.lower():
                                            ui.icon('check_circle', size='xs', color='green')
                                            ui.label(platform).classes('text-sm')
                                            ui.badge(f'{r.cashback_percent}%', color='green').props('dense')
                                        else:
                                            ui.icon('cancel', size='xs', color='gray')
                                            ui.label(platform).classes('text-sm text-gray-500')
                
                # Promo Code Sources
                with ui.card().classes('w-full bg-gray-800'):
                    ui.label('🏷️ Promo Code Sources').classes('font-semibold text-gray-300 mb-2')
                    
                    if r.search_transparency and r.search_transparency.promo_sources_checked:
                        with ui.column().classes('gap-1 w-full'):
                            for ps in r.search_transparency.promo_sources_checked:
                                with ui.row().classes('w-full justify-between items-center py-1'):
                                    with ui.row().classes('items-center gap-2'):
                                        if ps.codes_found > 0:
                                            ui.icon('check_circle', size='xs', color='amber')
                                        else:
                                            ui.icon('cancel', size='xs', color='gray')
                                        ui.label(ps.source).classes('text-sm')
                                    if ps.codes_found > 0:
                                        ui.badge(f'{ps.codes_found} codes', color='amber').props('dense')
                                    else:
                                        ui.label('No codes').classes('text-xs text-gray-500')
                    else:
                        sources = ['RetailMeNot', 'Honey', 'Vendor Site']
                        with ui.column().classes('gap-1 w-full'):
                            for source in sources:
                                with ui.row().classes('w-full justify-between items-center py-1'):
                                    ui.icon('cancel', size='xs', color='gray')
                                    ui.label(source).classes('text-sm text-gray-500')
                
                # Tax Source Info
                with ui.card().classes('w-full bg-gray-800'):
                    ui.label('📍 Tax Detection').classes('font-semibold text-gray-300 mb-2')
                    tax_source = "Default"
                    if r.search_transparency:
                        tax_source = r.search_transparency.tax_source.capitalize()
                    
                    with ui.row().classes('items-center gap-2'):
                        if tax_source == "Browser":
                            ui.icon('gps_fixed', size='xs', color='blue')
                            ui.label(f'Using your location: {r.tax_location or "Unknown"}').classes('text-sm')
                        elif tax_source == "Ip":
                            ui.icon('language', size='xs', color='yellow')
                            ui.label(f'Detected from IP: {r.tax_location or "Unknown"}').classes('text-sm')
                        else:
                            ui.icon('help', size='xs', color='gray')
                            ui.label('Using default rate').classes('text-sm text-gray-500')
                    
                    # Link to settings to set location
                    ui.button('Set Your Location', on_click=lambda: ui.navigate.to('/settings'), icon='edit_location').props('flat size=sm color=primary').classes('mt-2')
                
                # Search Duration
                if r.search_transparency and r.search_transparency.search_duration_ms > 0:
                    ui.label(f'⏱️ Search completed in {r.search_transparency.search_duration_ms}ms').classes('text-xs text-gray-500 mt-2')

def create_cards_page_content():
    """Create the card wallet management page."""
    ui.label('💳 My Credit Cards').classes('text-2xl font-bold mb-2')
    ui.label('Add your cards to see which one gives the best rewards').classes('text-gray-400 mb-6')
    
    # Current cards
    with ui.card().classes('w-full mb-6'):
        ui.label('Your Cards').classes('text-lg font-semibold mb-4')
        
        if not state.user_cards:
            with ui.column().classes('items-center py-8'):
                ui.icon('credit_card_off', size='xl', color='gray')
                ui.label('No cards added yet').classes('text-gray-400 mt-2')
                ui.label('Add cards below to see optimal rewards').classes('text-sm text-gray-500')
        else:
            with ui.column().classes('gap-2 w-full'):
                for card in state.user_cards:
                    with ui.card().classes('w-full bg-gray-800'):
                        with ui.row().classes('w-full justify-between items-center'):
                            with ui.column():
                                ui.label(card.name).classes('font-semibold')
                                ui.label(card.issuer).classes('text-sm text-gray-400')
                                if card.highlights:
                                    ui.label(' • '.join(card.highlights[:2])).classes('text-xs text-green-400')
                            
                            async def remove_card(name=card.name):
                                state.user_cards = [c for c in state.user_cards if c.name != name]
                                ui.notify(f'Removed {name}', type='info')
                                ui.navigate.reload()
                            
                            ui.button(icon='delete', on_click=remove_card).props('flat color=negative')
    
    # Popular cards to add
    with ui.card().classes('w-full'):
        ui.label('Popular Cards').classes('text-lg font-semibold mb-4')
        ui.label('Quick-add from our database').classes('text-sm text-gray-400 mb-4')
        
        # Hardcoded popular cards for demo
        popular = [
            UserCard("Chase Sapphire Preferred", "Chase", 1.0, ["3x Dining", "3x Travel", "2x Streaming"]),
            UserCard("Amex Gold", "American Express", 1.0, ["4x Restaurants", "4x Groceries", "3x Flights"]),
            UserCard("Citi Double Cash", "Citi", 2.0, ["2% on everything"]),
            UserCard("Chase Freedom Flex", "Chase", 1.0, ["5% Rotating", "3x Dining", "3x Drugstores"]),
            UserCard("Discover it", "Discover", 1.0, ["5% Rotating categories"]),
            UserCard("Amazon Prime Visa", "Chase", 5.0, ["5% Amazon", "2% Restaurants"]),
        ]
        
        with ui.row().classes('gap-4 flex-wrap'):
            for card in popular:
                # Skip if already in wallet
                if any(c.name == card.name for c in state.user_cards):
                    continue
                    
                with ui.card().classes('w-64 bg-gray-800 hover:bg-gray-700 cursor-pointer'):
                    with ui.column():
                        ui.label(card.name).classes('font-semibold')
                        ui.label(card.issuer).classes('text-sm text-gray-400')
                        ui.label(' • '.join(card.highlights[:2])).classes('text-xs text-green-400 mt-1')
                        
                        async def add_card(name=card.name, c=card):
                            if c not in state.user_cards:
                                state.user_cards.append(c)
                                ui.notify(f'Added {name}!', type='positive')
                                ui.navigate.reload()
                        
                        ui.button('Add', on_click=add_card, icon='add').props('flat color=primary size=sm').classes('mt-2')

def create_footer():
    """Create the application footer."""
    with ui.footer().classes('bg-gray-900'):
        with ui.row().classes('w-full justify-between items-center px-4'):
            ui.label('Net Price Finder v0.5.0').classes('text-gray-500 text-sm')
            with ui.row().classes('gap-4'):
                ui.link('Privacy', '#').classes('text-gray-500 text-sm')
                ui.link('GitHub', 'https://github.com').classes('text-gray-500 text-sm')

# =============================================================================
# Pages
# =============================================================================

@ui.page('/')
async def main_page():
    """Main search page."""
    state.redis_client = await init_redis()
    
    ui.dark_mode().enable()
    
    create_header()
    
    with ui.column().classes('w-full p-4 gap-6 max-w-5xl mx-auto'):
        create_search_hero()
        create_quick_calculator()
        create_how_it_works()
    
    create_footer()

@ui.page('/results')
async def results_page():
    """Results display page."""
    ui.dark_mode().enable()
    
    create_header()
    
    with ui.column().classes('w-full p-4 gap-4'):
        create_results_display()
    
    create_footer()

@ui.page('/cards')
async def cards_page():
    """Card wallet management page."""
    ui.dark_mode().enable()
    
    create_header()
    
    with ui.column().classes('w-full p-4 gap-4 max-w-4xl mx-auto'):
        ui.button('← Back', on_click=lambda: ui.navigate.to('/'), icon='arrow_back').props('flat')
        create_cards_page_content()
    
    create_footer()

@ui.page('/settings')
async def settings_page():
    """Settings page."""
    ui.dark_mode().enable()
    
    create_header()
    
    # US State tax rates for dropdown
    US_STATES = {
        "Alabama": 9.24, "Alaska": 1.76, "Arizona": 8.40, "Arkansas": 9.47,
        "California": 8.85, "Colorado": 7.77, "Connecticut": 6.35, "Delaware": 0.0,
        "Florida": 7.05, "Georgia": 7.38, "Hawaii": 4.50, "Idaho": 6.02,
        "Illinois": 8.82, "Indiana": 7.0, "Iowa": 6.94, "Kansas": 8.70,
        "Kentucky": 6.0, "Louisiana": 9.55, "Maine": 5.5, "Maryland": 6.0,
        "Massachusetts": 6.25, "Michigan": 6.0, "Minnesota": 7.505, "Mississippi": 7.07,
        "Missouri": 8.285, "Montana": 0.0, "Nebraska": 6.94, "Nevada": 8.23,
        "New Hampshire": 0.0, "New Jersey": 6.625, "New Mexico": 7.595, "New York": 8.52,
        "North Carolina": 6.98, "North Dakota": 7.04, "Ohio": 7.23, "Oklahoma": 8.97,
        "Oregon": 0.0, "Pennsylvania": 6.34, "Rhode Island": 7.0, "South Carolina": 7.44,
        "South Dakota": 6.10, "Tennessee": 9.55, "Texas": 8.20, "Utah": 7.19,
        "Vermont": 6.24, "Virginia": 5.75, "Washington": 9.23, "West Virginia": 6.52,
        "Wisconsin": 5.44, "Wyoming": 5.36, "Washington DC": 6.0
    }
    
    with ui.column().classes('w-full p-4 gap-4 max-w-2xl mx-auto'):
        ui.button('← Back', on_click=lambda: ui.navigate.to('/'), icon='arrow_back').props('flat')
        
        ui.label('⚙️ Settings').classes('text-2xl font-bold')
        
        # Tax Settings Card
        with ui.card().classes('w-full'):
            ui.label('📍 Your Location & Tax Rate').classes('font-semibold text-lg mb-2')
            ui.label('Set your location for accurate sales tax calculation').classes('text-sm text-gray-400 mb-4')
            
            # State Selection
            state_select = ui.select(
                options=list(US_STATES.keys()),
                label='Select Your State',
                value=state.user_location if state.user_location in US_STATES else None,
                on_change=lambda e: update_tax_from_state(e.value)
            ).classes('w-full')
            
            # Or manual tax rate
            ui.label('Or enter a custom tax rate:').classes('text-sm text-gray-400 mt-4')
            
            tax_input = ui.number(
                'Tax Rate (%)',
                value=state.user_tax_rate if state.user_tax_rate else 0,
                min=0,
                max=15,
                step=0.01,
                format='%.2f',
                suffix='%'
            ).classes('w-48')
            
            def update_tax_from_state(state_name):
                if state_name and state_name in US_STATES:
                    state.user_location = state_name
                    state.user_tax_rate = US_STATES[state_name]
                    tax_input.value = state.user_tax_rate
                    ui.notify(f'Tax rate set to {state.user_tax_rate}% for {state_name}', type='positive')
            
            def save_custom_tax():
                state.user_tax_rate = tax_input.value
                if not state.user_location:
                    state.user_location = "Custom"
                ui.notify(f'Tax rate saved: {state.user_tax_rate}%', type='positive')
            
            ui.button('Save Custom Rate', on_click=save_custom_tax, icon='save').props('color=primary').classes('mt-2')
            
            # Show current setting
            with ui.card().classes('w-full bg-gray-800 mt-4'):
                ui.label('Current Setting:').classes('text-sm text-gray-400')
                if state.user_tax_rate is not None:
                    ui.label(f'📍 {state.user_location or "Custom"}: {state.user_tax_rate}%').classes('text-lg text-green-400')
                else:
                    ui.label('🌐 Using IP-based detection (may be inaccurate)').classes('text-yellow-400')
            
            # Clear button
            def clear_location():
                state.user_tax_rate = None
                state.user_location = None
                state_select.value = None
                tax_input.value = 0
                ui.notify('Location cleared - will use IP detection', type='info')
            
            ui.button('Clear Location (Use Auto-Detect)', on_click=clear_location, icon='clear').props('flat color=warning').classes('mt-2')
        
        # Cashback Platforms Card
        with ui.card().classes('w-full'):
            ui.label('💵 Cashback Platforms').classes('font-semibold text-lg mb-2')
            ui.label('Select which platforms to check for cashback').classes('text-sm text-gray-400 mb-4')
            with ui.column().classes('gap-2'):
                ui.checkbox('Rakuten', value=True)
                ui.checkbox('TopCashback', value=True)
                ui.checkbox('Honey', value=True)
                ui.checkbox('BeFrugal', value=True)
                ui.checkbox('Swagbucks', value=True)
    
    create_footer()

@ui.page('/health')
async def health_check():
    """Health check endpoint for Docker."""
    return {'status': 'healthy', 'service': 'app-frontend', 'version': '0.5.0'}

# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        host='0.0.0.0',
        port=8080,
        title='Net Price Finder',
        favicon='💰',
        reload=False,
        show=False
    )
