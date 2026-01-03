"""
Net Price Finder API Server

FastAPI server that exposes the Net Price Optimizer and related
intelligence modules to the frontend.
"""

import os
import sys
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
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

class SavingsResponse(BaseModel):
    """Response with savings breakdown."""
    product_price: float
    retailer: str
    original_url: str
    coupon_code: Optional[str]
    coupon_discount: float
    tax: float
    shipping: float
    gross_total: float
    cashback_platform: Optional[str]
    cashback_percent: float
    cashback_value: float
    card_name: Optional[str]
    card_reward_percent: float
    card_reward_value: float
    net_price: float
    total_savings: float
    savings_percent: float
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
    yield
    # Shutdown
    print("👋 Net Price Finder API shutting down...")
    if app.state.optimizer:
        await app.state.optimizer.__aexit__(None, None, None)

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
async def find_best_price(request: ProductSearchRequest):
    """
    Find the best net price for a product.
    
    This endpoint:
    1. Scrapes the product page for price
    2. Searches cashback platforms (Rakuten, TopCashback, etc.)
    3. Finds applicable coupons
    4. Calculates credit card rewards (if user has cards configured)
    5. Returns the TRUE net price after all savings
    """
    try:
        # Create optimizer with user's wallet (if they have cards)
        wallet = app.state.user_wallet if app.state.user_wallet.cards else None
        
        async with NetPriceOptimizer(card_wallet=wallet) as optimizer:
            result = await optimizer.optimize(request.query)
            
            if not result:
                raise HTTPException(status_code=404, detail="Could not find product")
            
            return SavingsResponse(
                product_price=result.product_price,
                retailer=result.retailer,
                original_url=result.original_url,
                coupon_code=result.coupon_code,
                coupon_discount=result.coupon_discount,
                tax=result.tax,
                shipping=result.shipping,
                gross_total=result.gross_total,
                cashback_platform=result.cashback_platform,
                cashback_percent=result.cashback_percent,
                cashback_value=result.cashback_value,
                card_name=result.card_name,
                card_reward_percent=result.card_reward_percent,
                card_reward_value=result.card_reward_value,
                net_price=result.net_price,
                total_savings=result.total_savings,
                savings_percent=result.savings_percent,
                timestamp=datetime.now()
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/cashback-rates", response_model=CashbackRatesResponse)
async def get_cashback_rates(request: CashbackRatesRequest):
    """
    Get current cashback rates for a merchant across all platforms.
    """
    try:
        async with CashbackMonitor() as monitor:
            result = await monitor.get_best_cashback(request.merchant)
            
            return CashbackRatesResponse(
                merchant=request.merchant,
                best_platform=result.best_offer.platform if result.best_offer else None,
                best_rate=result.best_rate,
                rates=[
                    {
                        "platform": offer.platform,
                        "rate": offer.rate,
                        "type": offer.rate_type,
                        "terms": offer.terms
                    }
                    for offer in result.offers
                ]
            )
    except Exception as e:
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
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
