"""
Net Price Finder API Server

FastAPI server that exposes the Net Price Optimizer and related
intelligence modules to the frontend.
"""

import os
import sys
import logging
import traceback
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, HttpUrl
import uvicorn

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from optimizer.net_price import (
    NetPriceOptimizer,
    SavingsBreakdown,
    RetailerOption,
    calculate_net_price
)
from rewards.schema import (
    CreditCard,
    CardWallet,
    RewardRate,
    BonusCategory,
    POPULAR_CARDS
)
from cashback.monitor import CashbackMonitor, CashbackOffer
from tax.location import TaxCalculator, get_tax_rate_for_ip
from retailer.intelligence import RetailerIntelligence, get_intelligence

# =============================================================================
# Configuration
# =============================================================================

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://ollama:11434")
SCRAPER_API_URL = os.getenv("SCRAPER_API_URL", "http://scraper-engine:5000")

# =============================================================================
# Pydantic Models (API Contracts)
# =============================================================================

class ProductSearchRequest(BaseModel):
    """Request to find the best net price for a product."""
    query: str = Field(..., description="Product URL or search term")
    include_cashback: bool = Field(True, description="Search cashback platforms")
    include_coupons: bool = Field(True, description="Search for coupons")
    # User-provided tax info (from browser geolocation)
    user_tax_rate: Optional[float] = Field(None, description="Tax rate from user settings (0-15%)")
    user_location: Optional[str] = Field(None, description="User's location (state/city)")
    
class CardInfo(BaseModel):
    """Credit card information for the user's wallet."""
    name: str = Field(..., description="Card name (e.g., 'Chase Sapphire Preferred')")
    issuer: str = Field(..., description="Card issuer (e.g., 'Chase')")
    base_rate: float = Field(1.0, description="Base reward rate in %")
    bonus_categories: Optional[List[dict]] = Field(None, description="Bonus category rates")

class UserWallet(BaseModel):
    """User's credit card wallet."""
    cards: List[CardInfo] = Field(default_factory=list, description="User's credit cards")

class QuickPriceRequest(BaseModel):
    """Request for quick price calculation (no scraping)."""
    product_price: float = Field(..., gt=0)
    cashback_percent: float = Field(0, ge=0, le=100)
    card_reward_percent: float = Field(0, ge=0, le=100)
    coupon_discount: float = Field(0, ge=0)
    tax_rate: float = Field(0, ge=0, le=1)
    shipping: float = Field(0, ge=0)

class CashbackSearchResult(BaseModel):
    """Result from checking a single cashback platform."""
    platform: str
    rate: float = 0.0
    found: bool = False
    error: Optional[str] = None

class SearchTransparency(BaseModel):
    """Transparency into what was searched and found."""
    cashback_platforms_checked: List[CashbackSearchResult] = Field(default_factory=list)
    tax_source: str = "default"  # "browser", "ip", "default"
    search_duration_ms: int = 0

class SavingsResponse(BaseModel):
    """Response with savings breakdown."""
    product_name: str
    product_price: float
    retailer: str
    original_url: str
    coupon_code: Optional[str]
    coupon_discount: float
    tax: float
    tax_rate: float = 0.0
    tax_location: Optional[str] = None
    shipping: float
    gross_total: float
    cashback_platform: Optional[str]
    cashback_percent: float
    cashback_value: float
    # All cashback rates found (for transparency)
    all_cashback_rates: List[dict] = Field(default_factory=list)
    card_name: Optional[str]
    card_reward_percent: float
    card_reward_value: float
    net_price: float
    total_savings: float
    savings_percent: float
    # Search transparency
    search_transparency: Optional[SearchTransparency] = None
    timestamp: datetime

class CashbackRatesRequest(BaseModel):
    """Request to get cashback rates for a merchant."""
    merchant: str = Field(..., description="Merchant name (e.g., 'Nike', 'Amazon')")

class CashbackRatesResponse(BaseModel):
    """Response with cashback rates from all platforms."""
    merchant: str
    best_platform: Optional[str]
    best_rate: float
    rates: List[dict]

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    services: dict

# =============================================================================
# Application Lifespan
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("🚀 Net Price Finder API starting...")
    app.state.optimizer = None
    app.state.cashback_monitor = None
    app.state.user_wallet = CardWallet()
    
    # Initialize RetailerIntelligence for persistent caching
    try:
        app.state.intelligence = await get_intelligence()
        print("✅ RetailerIntelligence initialized")
    except Exception as e:
        print(f"⚠️ RetailerIntelligence init failed: {e}")
        app.state.intelligence = None
    
    yield
    # Shutdown
    print("👋 Net Price Finder API shutting down...")
    if app.state.optimizer:
        await app.state.optimizer.__aexit__(None, None, None)
    if app.state.intelligence:
        await app.state.intelligence.close()

# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Net Price Finder API",
    description="Find the TRUE cheapest price after all savings stack",
    version="0.5.0",
    lifespan=lifespan
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="0.5.0",
        services={
            "optimizer": "ready",
            "cashback_monitor": "ready",
            "card_wallet": f"{len(app.state.user_wallet.cards)} cards"
        }
    )

@app.post("/api/v1/quick-price")
async def quick_price_calculation(request: QuickPriceRequest):
    """
    Quick price calculation without scraping.
    
    Use this for instant calculations when you already know the values.
    """
    result = calculate_net_price(
        product_price=request.product_price,
        cashback_percent=request.cashback_percent,
        card_reward_percent=request.card_reward_percent,
        coupon_discount=request.coupon_discount,
        tax_rate=request.tax_rate,
        shipping=request.shipping
    )
    return result

@app.post("/api/v1/find-best-price", response_model=SavingsResponse)
async def find_best_price(request: ProductSearchRequest, req: Request):
    """
    Find the best net price for a product.
    
    This endpoint:
    1. Scrapes the product page for price
    2. Searches cashback platforms (Rakuten, TopCashback, etc.)
    3. Finds applicable coupons
    4. Calculates credit card rewards (if user has cards configured)
    5. Uses user-provided location for tax, or auto-detects from IP
    6. Returns the TRUE net price after all savings with full transparency
    """
    import time
    start_time = time.time()
    
    try:
        logger.info(f"Processing query: {request.query}")
        
        # Track search transparency
        cashback_results = []
        tax_source = "default"
        
        # Determine tax rate - prefer user-provided, then IP, then default
        tax_rate = 0.0
        tax_location = None
        
        if request.user_tax_rate is not None:
            # User provided tax rate from browser settings
            tax_rate = request.user_tax_rate / 100  # Convert from percentage
            tax_location = request.user_location or "User Settings"
            tax_source = "browser"
            logger.info(f"Using user-provided tax: {request.user_tax_rate}% for {tax_location}")
        else:
            # Try IP-based detection
            client_ip = req.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            if not client_ip:
                client_ip = req.client.host if req.client else None
            
            try:
                async with TaxCalculator() as tax_calc:
                    tax_info = await tax_calc.get_tax_for_ip(client_ip)
                    tax_rate = tax_info.combined_rate / 100  # Convert to decimal
                    tax_location = tax_info.state_name or tax_info.state_code
                    tax_source = "ip"
                    logger.info(f"Detected tax: {tax_info.combined_rate}% for {tax_location} (IP: {client_ip})")
            except Exception as e:
                logger.warning(f"Tax detection failed: {e}, using 0%")
                tax_source = "default"
        
        # Create optimizer with user's wallet (if they have cards) and detected tax rate
        wallet = app.state.user_wallet if app.state.user_wallet.cards else None
        
        async with NetPriceOptimizer(card_wallet=wallet, tax_rate=tax_rate) as optimizer:
            result = await optimizer.optimize(request.query)
            
            logger.info(f"Optimization result: options={len(result.options)}, best_option={result.best_option is not None}, error={result.error}")
            
            if not result.best_option:
                error_msg = result.error or "Could not find product or price"
                logger.error(f"No best option found: {error_msg}")
                raise HTTPException(status_code=404, detail=error_msg)
            
            # Extract data from the best option
            best = result.best_option
            savings = best.savings
            product = best.product
            
            logger.info(f"Best option: {product.name}, price=${savings.product_price}, net=${savings.net_price}")
            
            # Build cashback transparency data
            # Use ALL offers from optimization (not just the best one)
            platforms_checked = ["Rakuten", "TopCashback", "Honey", "BeFrugal", "Swagbucks"]
            all_rates = []
            
            # Build a map of platform -> offer from actual scraping results
            found_offers = {
                offer["platform"].lower(): offer
                for offer in result.all_cashback_offers
            }
            
            for platform in platforms_checked:
                platform_key = platform.lower()
                if platform_key in found_offers:
                    # This platform was actually found during scraping
                    offer = found_offers[platform_key]
                    is_best = (savings.cashback_platform and 
                              platform_key == savings.cashback_platform.lower())
                    cashback_results.append(CashbackSearchResult(
                        platform=platform,
                        rate=offer["rate"],
                        found=True
                    ))
                    all_rates.append({
                        "platform": platform,
                        "rate": offer["rate"],
                        "is_best": is_best
                    })
                else:
                    # Platform was checked but no offer found
                    cashback_results.append(CashbackSearchResult(
                        platform=platform,
                        rate=0.0,
                        found=False
                    ))
            
            search_duration = int((time.time() - start_time) * 1000)
            
            return SavingsResponse(
                product_name=product.name,
                product_price=savings.product_price,
                retailer=best.retailer,
                original_url=product.url,
                coupon_code=savings.coupon_code,
                coupon_discount=savings.coupon_savings,
                tax=savings.tax,
                tax_rate=tax_rate * 100,  # Convert to percentage
                tax_location=tax_location,
                shipping=savings.shipping,
                gross_total=savings.gross_total,
                cashback_platform=savings.cashback_platform,
                cashback_percent=savings.cashback_percent,
                cashback_value=savings.cashback_amount,
                all_cashback_rates=all_rates,
                card_name=savings.credit_card_name,
                card_reward_percent=savings.credit_card_rate,
                card_reward_value=savings.credit_card_rewards,
                net_price=savings.net_price,
                total_savings=savings.total_savings,
                savings_percent=savings.savings_percent,
                search_transparency=SearchTransparency(
                    cashback_platforms_checked=cashback_results,
                    tax_source=tax_source,
                    search_duration_ms=search_duration
                ),
                timestamp=datetime.now()
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in find_best_price: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/cashback-rates", response_model=CashbackRatesResponse)
async def get_cashback_rates(request: CashbackRatesRequest):
    """
    Get current cashback rates for a merchant across all platforms.
    """
    try:
        async with CashbackMonitor() as monitor:
            result = await monitor.find_best_cashback(request.merchant)
            
            best_rate = result.best_offer.effective_rate if result.best_offer else 0.0
            
            return CashbackRatesResponse(
                merchant=request.merchant,
                best_platform=result.best_offer.platform.value if result.best_offer else None,
                best_rate=best_rate,
                rates=[
                    {
                        "platform": offer.platform.value,
                        "rate": offer.effective_rate,
                        "type": "percent" if offer.cashback_percent else "fixed",
                        "terms": offer.cashback_text or ""
                    }
                    for offer in result.offers
                ]
            )
    except Exception as e:
        logger.error(f"Error getting cashback rates: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =============================================================================
# Card Wallet Management
# =============================================================================

@app.get("/api/v1/wallet")
async def get_wallet():
    """Get the user's current card wallet."""
    return {
        "cards": [
            {
                "name": card.name,
                "issuer": card.issuer,
                "base_rate": card.base_rate,
                "bonus_categories": [
                    {"category": bc.category, "rate": bc.rate}
                    for bc in card.bonus_categories
                ]
            }
            for card in app.state.user_wallet.cards
        ],
        "card_count": len(app.state.user_wallet.cards)
    }

@app.post("/api/v1/wallet/add")
async def add_card_to_wallet(card: CardInfo):
    """Add a card to the user's wallet."""
    new_card = CreditCard(
        name=card.name,
        issuer=card.issuer,
        base_rate=card.base_rate,
        bonus_categories=[
            BonusCategory(category=bc.get("category", ""), rate=bc.get("rate", 1.0))
            for bc in (card.bonus_categories or [])
        ]
    )
    app.state.user_wallet.add_card(new_card)
    return {"status": "added", "card": card.name, "total_cards": len(app.state.user_wallet.cards)}

@app.delete("/api/v1/wallet/{card_name}")
async def remove_card_from_wallet(card_name: str):
    """Remove a card from the user's wallet."""
    app.state.user_wallet.cards = [
        c for c in app.state.user_wallet.cards if c.name != card_name
    ]
    return {"status": "removed", "card": card_name, "total_cards": len(app.state.user_wallet.cards)}

@app.get("/api/v1/popular-cards")
async def get_popular_cards():
    """Get list of popular pre-built cards that users can add."""
    return {
        "cards": [
            {
                "name": card.name,
                "issuer": card.issuer,
                "base_rate": card.base_rate,
                "highlights": [
                    f"{bc.rate}x on {bc.category}"
                    for bc in card.bonus_categories[:3]
                ]
            }
            for card in POPULAR_CARDS
        ]
    }

@app.post("/api/v1/wallet/add-popular/{card_name}")
async def add_popular_card(card_name: str):
    """Add a popular pre-built card to the user's wallet."""
    card = next((c for c in POPULAR_CARDS if c.name == card_name), None)
    if not card:
        raise HTTPException(status_code=404, detail=f"Card '{card_name}' not found")
    
    app.state.user_wallet.add_card(card)
    return {"status": "added", "card": card_name, "total_cards": len(app.state.user_wallet.cards)}


# =============================================================================
# Retailer Intelligence Endpoints
# =============================================================================

@app.get("/api/v1/retailer/{name}/deals")
async def get_retailer_deals(name: str, force_refresh: bool = False):
    """
    Get all cashback and promo deals for a retailer.
    
    Returns cached data if available, otherwise triggers fresh scrape.
    Use force_refresh=true to force a new scrape.
    """
    if not app.state.intelligence:
        raise HTTPException(
            status_code=503, 
            detail="RetailerIntelligence not available"
        )
    
    try:
        deals = await app.state.intelligence.get_deals(
            name, 
            force_refresh=force_refresh
        )
        return deals.to_dict()
    except Exception as e:
        logger.error(f"Error getting deals for {name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/retailer/{name}/strategy")
async def get_savings_strategy(
    name: str, 
    amount: float = 100.0,
    category: Optional[str] = None,
):
    """
    Get optimal savings strategy for a purchase at a retailer.
    
    Args:
        name: Retailer name
        amount: Purchase amount in dollars
        category: Product category for credit card rewards
    """
    if not app.state.intelligence:
        raise HTTPException(
            status_code=503,
            detail="RetailerIntelligence not available"
        )
    
    try:
        strategy = await app.state.intelligence.get_best_strategy(
            name,
            purchase_amount=amount,
            card_wallet=app.state.user_wallet if app.state.user_wallet.cards else None,
            product_category=category,
        )
        return strategy.to_dict()
    except Exception as e:
        logger.error(f"Error getting strategy for {name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/retailer/{name}/refresh")
async def refresh_retailer_data(name: str):
    """
    Force refresh all data for a retailer.
    
    Triggers fresh scrape of all cashback platforms.
    """
    if not app.state.intelligence:
        raise HTTPException(
            status_code=503,
            detail="RetailerIntelligence not available"
        )
    
    try:
        deals = await app.state.intelligence.refresh_retailer(name)
        return {
            "status": "refreshed",
            "retailer": name,
            "offers_found": len(deals.cashback_offers),
            "promos_found": len(deals.promo_codes),
            "sources": deals.data_sources,
        }
    except Exception as e:
        logger.error(f"Error refreshing {name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/intelligence/stats")
async def get_intelligence_stats():
    """Get statistics for the retailer intelligence system."""
    if not app.state.intelligence:
        return {
            "available": False,
            "message": "RetailerIntelligence not initialized"
        }
    
    try:
        stats = await app.state.intelligence.get_stats()
        top_retailers = await app.state.intelligence.get_top_retailers(10)
        platform_status = await app.state.intelligence.get_platform_status()
        
        return {
            "available": True,
            **stats,
            "top_retailers": top_retailers,
            "platform_status": platform_status,
        }
    except Exception as e:
        logger.error(f"Error getting intelligence stats: {e}")
        return {
            "available": False,
            "error": str(e)
        }


@app.get("/api/v1/intelligence/stale")
async def get_stale_retailers(max_age_hours: int = 24):
    """Get list of retailers that need refresh."""
    if not app.state.intelligence:
        raise HTTPException(
            status_code=503,
            detail="RetailerIntelligence not available"
        )
    
    stale = await app.state.intelligence.get_stale_retailers(max_age_hours)
    return {
        "stale_count": len(stale),
        "retailers": stale[:50],  # Limit to 50
        "max_age_hours": max_age_hours,
    }


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
