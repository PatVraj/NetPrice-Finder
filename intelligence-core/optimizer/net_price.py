"""
Net Price Optimizer for SSIP
The core intelligence that finds the TRUE cheapest price for any product.

Given a product URL or description, calculates net cost after:
1. Retailer price (and alternatives)
2. Cashback platforms (Rakuten, Honey, TopCashback, etc.)
3. Credit card rewards (optimal card for the category)
4. Available coupons/promo codes
5. PayPal/wallet offers
"""

import os
import re
import json
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse, quote_plus
from enum import Enum

import httpx


# =============================================================================
# Configuration
# =============================================================================

SCRAPER_HOST = os.getenv("SCRAPER_HOST", "http://scraper-engine:8000")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")


class PaymentMethod(Enum):
    """Available payment methods."""
    CREDIT_CARD = "credit_card"
    PAYPAL = "paypal"
    DEBIT = "debit"
    GIFT_CARD = "gift_card"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"


@dataclass
class ProductInfo:
    """Information about a product from a retailer."""
    name: str
    price: float
    currency: str = "USD"
    retailer: str = ""
    url: Optional[str] = None
    
    # Additional details
    category: Optional[str] = None
    mcc_code: Optional[str] = None  # For credit card rewards
    in_stock: bool = True
    shipping_cost: float = 0.0
    estimated_tax: float = 0.0
    
    # Original price if on sale
    original_price: Optional[float] = None
    discount_percent: Optional[float] = None
    
    # Metadata
    scraped_at: Optional[str] = None
    confidence: float = 1.0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @property
    def total_before_savings(self) -> float:
        """Total price before any cashback/rewards."""
        return self.price + self.shipping_cost + self.estimated_tax


@dataclass 
class CouponResult:
    """Result of testing a coupon code."""
    code: str
    source: str  # Where we found it (RetailMeNot, etc.)
    works: bool
    discount_amount: float = 0.0
    discount_percent: float = 0.0
    final_price: Optional[float] = None
    terms: Optional[str] = None
    expires: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SavingsBreakdown:
    """Breakdown of all savings for a purchase."""
    # Base price
    product_price: float
    shipping: float = 0.0
    tax: float = 0.0
    
    # Savings sources
    coupon_savings: float = 0.0
    coupon_code: Optional[str] = None
    
    cashback_amount: float = 0.0
    cashback_platform: Optional[str] = None
    cashback_percent: float = 0.0
    
    credit_card_rewards: float = 0.0  # Cash value of points/miles
    credit_card_name: Optional[str] = None
    credit_card_rate: float = 0.0  # e.g., 3% or 3x
    
    paypal_cashback: float = 0.0
    
    # Totals
    gross_total: float = 0.0  # Before any savings
    total_savings: float = 0.0
    net_price: float = 0.0  # What you actually "pay" after rewards
    
    # Comparison
    savings_percent: float = 0.0  # Total savings as % of gross
    
    def calculate_totals(self):
        """Calculate all totals from components."""
        self.gross_total = self.product_price + self.shipping + self.tax
        self.total_savings = (
            self.coupon_savings +
            self.cashback_amount +
            self.credit_card_rewards +
            self.paypal_cashback
        )
        self.net_price = self.gross_total - self.total_savings
        if self.gross_total > 0:
            self.savings_percent = (self.total_savings / self.gross_total) * 100
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetailerOption:
    """A purchase option from a specific retailer."""
    retailer: str
    product: ProductInfo
    savings: SavingsBreakdown
    
    # Recommendations
    recommended_card: Optional[str] = None
    recommended_cashback: Optional[str] = None
    recommended_coupon: Optional[str] = None
    
    # Stacking instructions
    steps: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "retailer": self.retailer,
            "product": self.product.to_dict(),
            "savings": self.savings.to_dict(),
            "recommended_card": self.recommended_card,
            "recommended_cashback": self.recommended_cashback,
            "recommended_coupon": self.recommended_coupon,
            "steps": self.steps,
        }


@dataclass
class OptimizationResult:
    """Complete result of price optimization."""
    query: str  # Original user query
    query_type: str  # "url" or "search"
    
    # All retailer options, sorted by net price
    options: list[RetailerOption] = field(default_factory=list)
    
    # Best option
    best_option: Optional[RetailerOption] = None
    
    # Comparison stats
    cheapest_gross: float = 0.0
    cheapest_net: float = 0.0
    max_savings: float = 0.0
    
    # Metadata
    processed_at: Optional[str] = None
    processing_time_ms: int = 0
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "query_type": self.query_type,
            "options": [o.to_dict() for o in self.options],
            "best_option": self.best_option.to_dict() if self.best_option else None,
            "cheapest_gross": self.cheapest_gross,
            "cheapest_net": self.cheapest_net,
            "max_savings": self.max_savings,
            "processed_at": self.processed_at,
            "processing_time_ms": self.processing_time_ms,
            "error": self.error,
        }


# =============================================================================
# Retailer Detection & Scraping
# =============================================================================

# Known retailers and their categories (for credit card rewards)
KNOWN_RETAILERS = {
    # General/Online
    "amazon.com": {"name": "Amazon", "category": "online_shopping", "mcc": "5999"},
    "amazon.co.uk": {"name": "Amazon UK", "category": "online_shopping", "mcc": "5999"},
    "ebay.com": {"name": "eBay", "category": "online_shopping", "mcc": "5999"},
    "walmart.com": {"name": "Walmart", "category": "retail", "mcc": "5311"},
    "target.com": {"name": "Target", "category": "retail", "mcc": "5311"},
    "costco.com": {"name": "Costco", "category": "wholesale", "mcc": "5300"},
    
    # Electronics
    "bestbuy.com": {"name": "Best Buy", "category": "electronics", "mcc": "5732"},
    "newegg.com": {"name": "Newegg", "category": "electronics", "mcc": "5732"},
    "bhphotovideo.com": {"name": "B&H Photo", "category": "electronics", "mcc": "5732"},
    "apple.com": {"name": "Apple", "category": "electronics", "mcc": "5732"},
    
    # Clothing
    "nike.com": {"name": "Nike", "category": "clothing", "mcc": "5651"},
    "adidas.com": {"name": "Adidas", "category": "clothing", "mcc": "5651"},
    "nordstrom.com": {"name": "Nordstrom", "category": "clothing", "mcc": "5651"},
    "macys.com": {"name": "Macy's", "category": "clothing", "mcc": "5311"},
    "gap.com": {"name": "Gap", "category": "clothing", "mcc": "5651"},
    "oldnavy.com": {"name": "Old Navy", "category": "clothing", "mcc": "5651"},
    
    # Home
    "homedepot.com": {"name": "Home Depot", "category": "home_improvement", "mcc": "5200"},
    "lowes.com": {"name": "Lowe's", "category": "home_improvement", "mcc": "5200"},
    "wayfair.com": {"name": "Wayfair", "category": "home", "mcc": "5712"},
    "ikea.com": {"name": "IKEA", "category": "home", "mcc": "5712"},
    
    # Beauty
    "sephora.com": {"name": "Sephora", "category": "beauty", "mcc": "5977"},
    "ulta.com": {"name": "Ulta", "category": "beauty", "mcc": "5977"},
    
    # Groceries
    "instacart.com": {"name": "Instacart", "category": "groceries", "mcc": "5411"},
    "freshdirect.com": {"name": "FreshDirect", "category": "groceries", "mcc": "5411"},
    "wholefoodsmarket.com": {"name": "Whole Foods", "category": "groceries", "mcc": "5411"},
}


def detect_retailer(url: str) -> Optional[dict]:
    """Detect retailer from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Remove www. prefix
        if domain.startswith("www."):
            domain = domain[4:]
        
        return KNOWN_RETAILERS.get(domain)
    except Exception:
        return None


def extract_domain(url: str) -> str:
    """Extract clean domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


# =============================================================================
# Product Scraper
# =============================================================================

class ProductScraper:
    """Scrapes product information from retailer pages."""
    
    def __init__(self, scraper_host: str = SCRAPER_HOST, timeout: float = 60.0):
        self.scraper_host = scraper_host.rstrip("/")
        self.timeout = timeout
    
    async def scrape_url(self, url: str) -> Optional[ProductInfo]:
        """
        Scrape product info from a URL.
        
        Uses the scraper-engine to render JavaScript and extract data.
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                # Call scraper engine to navigate and extract
                response = await client.post(
                    f"{self.scraper_host}/extract",
                    json={
                        "url": url,
                        "selectors": {
                            "title": [
                                "h1[data-testid='product-title']",
                                "h1.product-title",
                                "h1#productTitle",
                                "h1[itemprop='name']",
                                "h1",
                            ],
                            "price": [
                                "[data-testid='price']",
                                ".price-current",
                                ".a-price .a-offscreen",
                                "[itemprop='price']",
                                ".price",
                            ],
                            "original_price": [
                                ".price-was",
                                ".a-text-strike",
                                ".original-price",
                                "[data-testid='was-price']",
                            ],
                        },
                    },
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_scraped_data(data, url)
                    
            except Exception:
                pass
        
        return None
    
    async def scrape_with_llm(self, url: str, html: str) -> Optional[ProductInfo]:
        """
        Use LLM to extract product info from HTML.
        
        Fallback when structured selectors fail.
        """
        prompt = f"""Extract product information from this webpage HTML.
        
Return a JSON object with:
- name: Product name/title
- price: Current price (number only, no currency symbol)
- original_price: Original price if on sale (number only)
- in_stock: true/false

HTML (truncated):
{html[:5000]}

JSON:"""

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={
                        "model": "llama3.1:8b",
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.1},
                    },
                )
                
                if response.status_code == 200:
                    result = response.json()
                    text = result.get("response", "")
                    
                    # Extract JSON from response
                    json_match = re.search(r"\{[\s\S]*\}", text)
                    if json_match:
                        data = json.loads(json_match.group())
                        retailer_info = detect_retailer(url)
                        
                        return ProductInfo(
                            name=data.get("name", "Unknown Product"),
                            price=float(data.get("price", 0)),
                            original_price=data.get("original_price"),
                            in_stock=data.get("in_stock", True),
                            retailer=retailer_info.get("name", "") if retailer_info else "",
                            category=retailer_info.get("category") if retailer_info else None,
                            mcc_code=retailer_info.get("mcc") if retailer_info else None,
                            url=url,
                            scraped_at=datetime.now().isoformat(),
                        )
                        
            except Exception:
                pass
        
        return None
    
    def _parse_scraped_data(self, data: dict, url: str) -> Optional[ProductInfo]:
        """Parse scraped data into ProductInfo."""
        title = data.get("title", "")
        price_text = data.get("price", "")
        original_text = data.get("original_price", "")
        
        # Parse price
        price = self._parse_price(price_text)
        if price is None:
            return None
        
        original_price = self._parse_price(original_text) if original_text else None
        
        # Get retailer info
        retailer_info = detect_retailer(url)
        
        # Calculate discount
        discount_percent = None
        if original_price and original_price > price:
            discount_percent = ((original_price - price) / original_price) * 100
        
        return ProductInfo(
            name=title,
            price=price,
            original_price=original_price,
            discount_percent=discount_percent,
            retailer=retailer_info.get("name", "") if retailer_info else extract_domain(url),
            category=retailer_info.get("category") if retailer_info else None,
            mcc_code=retailer_info.get("mcc") if retailer_info else None,
            url=url,
            scraped_at=datetime.now().isoformat(),
        )
    
    def _parse_price(self, text: str) -> Optional[float]:
        """Parse price from text like '$99.99' or '99.99'."""
        if not text:
            return None
        
        # Remove currency symbols and whitespace
        cleaned = re.sub(r"[^\d.,]", "", text)
        
        # Handle comma as thousands separator
        cleaned = cleaned.replace(",", "")
        
        try:
            return float(cleaned)
        except ValueError:
            return None


# =============================================================================
# Coupon Finder & Tester
# =============================================================================

class CouponFinder:
    """Finds and tests coupon codes for retailers."""
    
    # Known coupon aggregator sources
    SOURCES = [
        "retailmenot",
        "coupons.com",
        "groupon",
        "honey",
        "slickdeals",
    ]
    
    def __init__(self, scraper_host: str = SCRAPER_HOST):
        self.scraper_host = scraper_host.rstrip("/")
    
    async def find_coupons(self, retailer: str) -> list[dict]:
        """
        Find available coupon codes for a retailer.
        
        Scrapes coupon aggregator sites for codes.
        """
        coupons = []
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try RetailMeNot
            try:
                slug = retailer.lower().replace(" ", "-").replace("'", "")
                response = await client.get(
                    f"https://www.retailmenot.com/view/{slug}.com",
                    headers={"User-Agent": "Mozilla/5.0"},
                    follow_redirects=True,
                )
                
                if response.status_code == 200:
                    html = response.text
                    
                    # Extract coupon codes (simplified pattern)
                    code_pattern = r'data-code="([A-Z0-9]+)"'
                    matches = re.findall(code_pattern, html, re.IGNORECASE)
                    
                    for code in matches[:5]:  # Top 5 codes
                        coupons.append({
                            "code": code.upper(),
                            "source": "RetailMeNot",
                            "terms": None,
                        })
                        
            except Exception:
                pass
            
            # Try generic search for common patterns
            common_codes = self._generate_common_codes(retailer)
            for code in common_codes:
                coupons.append({
                    "code": code,
                    "source": "common_patterns",
                    "terms": "May not be active",
                })
        
        return coupons
    
    def _generate_common_codes(self, retailer: str) -> list[str]:
        """Generate common coupon code patterns to try."""
        name = retailer.upper().replace(" ", "")[:4]
        codes = [
            f"{name}10",
            f"{name}15",
            f"{name}20",
            "SAVE10",
            "SAVE15",
            "SAVE20",
            "WELCOME10",
            "WELCOME15",
            "NEWCUSTOMER",
            "FREESHIP",
            "SHIPFREE",
        ]
        return codes
    
    async def test_coupon(
        self,
        retailer_url: str,
        code: str,
        original_price: float,
    ) -> CouponResult:
        """
        Test if a coupon code works by simulating checkout.
        
        Uses scraper-engine to add item to cart and try the code.
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{self.scraper_host}/test_coupon",
                    json={
                        "url": retailer_url,
                        "code": code,
                        "original_price": original_price,
                    },
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return CouponResult(
                        code=code,
                        source="test",
                        works=data.get("works", False),
                        discount_amount=data.get("discount", 0),
                        final_price=data.get("final_price"),
                    )
                    
            except Exception:
                pass
        
        # Couldn't test - return as unknown
        return CouponResult(
            code=code,
            source="untested",
            works=False,
        )


# =============================================================================
# Net Price Optimizer (Main Class)
# =============================================================================

class NetPriceOptimizer:
    """
    The core intelligence that finds the TRUE cheapest price.
    
    Calculates net cost after stacking:
    - Cashback platforms (Rakuten, Honey, TopCashback, etc.)
    - Credit card rewards (OPTIONAL - only if user provides their cards)
    - Coupon codes (OPTIONAL - requires checkout simulation)
    - Tax estimation
    
    Credit card rewards are ONLY calculated if the user provides their
    CardWallet. The optimizer will never assume which cards the user has.
    
    Usage:
        # Without credit cards (cashback only)
        async with NetPriceOptimizer() as optimizer:
            result = await optimizer.optimize("https://nike.com/product/...")
        
        # With user's credit cards
        from intelligence_core.rewards import CardWallet
        my_wallet = CardWallet()
        my_wallet.add_card(my_sapphire_preferred)
        my_wallet.add_card(my_amex_gold)
        
        async with NetPriceOptimizer(card_wallet=my_wallet) as optimizer:
            result = await optimizer.optimize("https://nike.com/product/...")
            print(f"Use {result.best_option.recommended_card}")  # From YOUR cards
    """
    
    def __init__(
        self,
        card_wallet: Optional[Any] = None,  # User's CardWallet (optional)
        enable_coupon_testing: bool = False,  # Disabled by default (slow)
        tax_rate: float = 0.0,  # State sales tax rate
    ):
        """
        Initialize the optimizer.
        
        Args:
            card_wallet: OPTIONAL - CardWallet with the user's actual credit cards.
                         If None, credit card rewards are NOT calculated.
                         Only the user's own cards are considered.
            enable_coupon_testing: Whether to test coupons at checkout (slow)
            tax_rate: Estimated sales tax rate (e.g., 0.0825 for 8.25%)
        """
        self.card_wallet = card_wallet
        self.enable_coupon_testing = enable_coupon_testing
        self.tax_rate = tax_rate
        
        self.product_scraper = ProductScraper()
        self.coupon_finder = CouponFinder()
        
        # Lazy imports to avoid circular dependencies
        self._cashback_monitor = None
    
    async def _get_cashback_monitor(self):
        """Lazy load cashback monitor."""
        if self._cashback_monitor is None:
            from .cashback import CashbackMonitor
            self._cashback_monitor = CashbackMonitor()
        return self._cashback_monitor
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._cashback_monitor:
            await self._cashback_monitor.close()
    
    def _is_url(self, query: str) -> bool:
        """Check if query is a URL."""
        return query.startswith("http://") or query.startswith("https://")
    
    async def optimize(self, query: str) -> OptimizationResult:
        """
        Find the best net price for a product.
        
        Args:
            query: Product URL or search term
            
        Returns:
            OptimizationResult with all options and best choice
        """
        start_time = asyncio.get_event_loop().time()
        
        result = OptimizationResult(
            query=query,
            query_type="url" if self._is_url(query) else "search",
            processed_at=datetime.now().isoformat(),
        )
        
        try:
            if self._is_url(query):
                options = await self._optimize_url(query)
            else:
                options = await self._optimize_search(query)
            
            result.options = options
            
            if options:
                # Sort by net price
                options.sort(key=lambda o: o.savings.net_price)
                result.best_option = options[0]
                
                # Calculate comparison stats
                result.cheapest_net = options[0].savings.net_price
                result.cheapest_gross = min(o.savings.gross_total for o in options)
                result.max_savings = max(o.savings.total_savings for o in options)
                
        except Exception as e:
            result.error = str(e)
        
        result.processing_time_ms = int(
            (asyncio.get_event_loop().time() - start_time) * 1000
        )
        
        return result
    
    async def _optimize_url(self, url: str) -> list[RetailerOption]:
        """Optimize a specific product URL."""
        options = []
        
        # 1. Scrape product info
        product = await self.product_scraper.scrape_url(url)
        
        if not product:
            # Create basic product from URL
            retailer_info = detect_retailer(url)
            product = ProductInfo(
                name="Product",
                price=0,
                retailer=retailer_info.get("name", "") if retailer_info else "",
                category=retailer_info.get("category") if retailer_info else None,
                mcc_code=retailer_info.get("mcc") if retailer_info else None,
                url=url,
            )
        
        # 2. Calculate savings for this retailer
        option = await self._calculate_savings(product)
        if option:
            options.append(option)
        
        # 3. TODO: Search for same product on other retailers
        # This would require product matching across sites
        
        return options
    
    async def _optimize_search(self, query: str) -> list[RetailerOption]:
        """Optimize based on a search query (product name)."""
        options = []
        
        # TODO: Search multiple retailers for the product
        # For now, return empty - would need product search APIs
        
        # Could search:
        # - Google Shopping API
        # - Amazon Product Advertising API
        # - Individual retailer search pages
        
        return options
    
    async def _calculate_savings(self, product: ProductInfo) -> Optional[RetailerOption]:
        """Calculate all savings for a product."""
        
        # Initialize savings breakdown
        savings = SavingsBreakdown(
            product_price=product.price,
            shipping=product.shipping_cost,
            tax=product.price * self.tax_rate if self.tax_rate > 0 else product.estimated_tax,
        )
        
        steps = []
        
        # 1. Find best cashback
        cashback_monitor = await self._get_cashback_monitor()
        retailer_name = product.retailer or "Unknown"
        
        try:
            cashback_result = await cashback_monitor.find_best_cashback(retailer_name)
            
            if cashback_result.best_offer:
                offer = cashback_result.best_offer
                savings.cashback_platform = offer.platform.value
                savings.cashback_percent = offer.effective_rate
                savings.cashback_amount = product.price * (offer.effective_rate / 100)
                
                steps.append(
                    f"Go through {offer.platform.value.title()} for {offer.cashback_text}"
                )
        except Exception:
            pass
        
        # 2. Find best credit card
        if self.card_wallet and product.category:
            try:
                best_card, card_info = self.card_wallet.get_best_card(
                    product.category,
                    product.price,
                )
                
                savings.credit_card_name = best_card.name
                savings.credit_card_rate = card_info["rate"]
                savings.credit_card_rewards = card_info["cash_value"]
                
                rate_str = f"{card_info['rate']}%" if card_info["reward_type"] == "cashback" else f"{card_info['rate']}x"
                steps.append(
                    f"Pay with {best_card.issuer} {best_card.name} ({rate_str} on {product.category})"
                )
            except Exception:
                pass
        
        # 3. Find coupons
        if self.enable_coupon_testing and product.url:
            try:
                coupons = await self.coupon_finder.find_coupons(retailer_name)
                
                # Test top coupons
                best_coupon = None
                best_discount = 0
                
                for coupon in coupons[:3]:  # Test top 3
                    result = await self.coupon_finder.test_coupon(
                        product.url,
                        coupon["code"],
                        product.price,
                    )
                    
                    if result.works and result.discount_amount > best_discount:
                        best_coupon = result
                        best_discount = result.discount_amount
                
                if best_coupon:
                    savings.coupon_code = best_coupon.code
                    savings.coupon_savings = best_coupon.discount_amount
                    steps.append(f"Apply coupon code: {best_coupon.code}")
                    
            except Exception:
                pass
        
        # Calculate totals
        savings.calculate_totals()
        
        # Build step-by-step instructions
        if not steps:
            steps.append("No special savings found - pay normally")
        
        steps.append(f"Net effective price: ${savings.net_price:.2f}")
        
        return RetailerOption(
            retailer=retailer_name,
            product=product,
            savings=savings,
            recommended_card=savings.credit_card_name,
            recommended_cashback=savings.cashback_platform,
            recommended_coupon=savings.coupon_code,
            steps=steps,
        )


# =============================================================================
# Convenience Functions
# =============================================================================

async def find_best_price(url: str, card_wallet: Any = None) -> OptimizationResult:
    """
    Quick helper to find the best net price for a product URL.
    
    Args:
        url: Product URL
        card_wallet: Optional CardWallet for credit card optimization
        
    Returns:
        OptimizationResult with best options
    """
    async with NetPriceOptimizer(card_wallet=card_wallet) as optimizer:
        return await optimizer.optimize(url)


async def compare_retailers(product_name: str, card_wallet: Any = None) -> OptimizationResult:
    """
    Compare prices across retailers for a product.
    
    Args:
        product_name: Name of product to search
        card_wallet: Optional CardWallet for credit card optimization
        
    Returns:
        OptimizationResult with all retailer options
    """
    async with NetPriceOptimizer(card_wallet=card_wallet) as optimizer:
        return await optimizer.optimize(product_name)


def calculate_net_price(
    product_price: float,
    cashback_percent: float = 0,
    card_reward_percent: float = 0,
    coupon_discount: float = 0,
    tax_rate: float = 0,
    shipping: float = 0,
) -> dict:
    """
    Quick calculation of net price given savings.
    
    Returns dict with breakdown.
    """
    subtotal = product_price - coupon_discount
    tax = subtotal * tax_rate
    gross = subtotal + tax + shipping
    
    cashback = product_price * (cashback_percent / 100)
    card_rewards = product_price * (card_reward_percent / 100)
    
    net_price = gross - cashback - card_rewards
    total_savings = coupon_discount + cashback + card_rewards
    
    return {
        "product_price": product_price,
        "coupon_discount": coupon_discount,
        "subtotal": subtotal,
        "tax": tax,
        "shipping": shipping,
        "gross_total": gross,
        "cashback": cashback,
        "card_rewards": card_rewards,
        "total_savings": total_savings,
        "net_price": net_price,
        "savings_percent": (total_savings / product_price * 100) if product_price > 0 else 0,
    }


# =============================================================================
# CLI for Testing
# =============================================================================

if __name__ == "__main__":
    import sys
    
    async def main():
        print("🏷️ Net Price Optimizer Demo\n")
        print("=" * 50)
        
        # Demo 1: WITHOUT credit cards (cashback + coupons only)
        print("\n📌 SCENARIO 1: Without Credit Cards")
        print("   (User has not added any cards to their wallet)\n")
        
        demo_no_cards = calculate_net_price(
            product_price=120.00,
            cashback_percent=6,      # TopCashback 6%
            card_reward_percent=0,   # No cards provided
            coupon_discount=18,      # NIKE15 coupon ($15 off)
            tax_rate=0.0825,
        )
        print(f"   Product Price:     ${demo_no_cards['product_price']:>8.2f}")
        print(f"   Coupon (NIKE15):  -${demo_no_cards['coupon_discount']:>8.2f}")
        print(f"   Tax (8.25%):      +${demo_no_cards['tax']:>8.2f}")
        print(f"   ─────────────────────────────")
        print(f"   Subtotal:          ${demo_no_cards['gross_total']:>8.2f}")
        print(f"   Cashback (6%):    -${demo_no_cards['cashback']:>8.2f}")
        print(f"   Credit Card:      -$    0.00  (none configured)")
        print(f"   ═════════════════════════════")
        print(f"   💰 NET PRICE:      ${demo_no_cards['net_price']:>8.2f}")
        print(f"   📊 Total Savings:  ${demo_no_cards['total_savings']:>8.2f} ({demo_no_cards['savings_percent']:.1f}%)")
        
        # Demo 2: WITH user's credit cards
        print("\n" + "=" * 50)
        print("\n📌 SCENARIO 2: With User's Credit Cards")
        print("   (User has Amex Gold earning 4x on this category)\n")
        
        demo_with_cards = calculate_net_price(
            product_price=120.00,
            cashback_percent=6,      # TopCashback 6%
            card_reward_percent=4,   # User's Amex Gold (4x on clothing)
            coupon_discount=18,      # NIKE15 coupon
            tax_rate=0.0825,
        )
        print(f"   Product Price:     ${demo_with_cards['product_price']:>8.2f}")
        print(f"   Coupon (NIKE15):  -${demo_with_cards['coupon_discount']:>8.2f}")
        print(f"   Tax (8.25%):      +${demo_with_cards['tax']:>8.2f}")
        print(f"   ─────────────────────────────")
        print(f"   Subtotal:          ${demo_with_cards['gross_total']:>8.2f}")
        print(f"   Cashback (6%):    -${demo_with_cards['cashback']:>8.2f}")
        print(f"   Amex Gold (4%):   -${demo_with_cards['card_rewards']:>8.2f}")
        print(f"   ═════════════════════════════")
        print(f"   💰 NET PRICE:      ${demo_with_cards['net_price']:>8.2f}")
        print(f"   📊 Total Savings:  ${demo_with_cards['total_savings']:>8.2f} ({demo_with_cards['savings_percent']:.1f}%)")
        
        # Show the difference
        print("\n" + "=" * 50)
        extra_savings = demo_no_cards['net_price'] - demo_with_cards['net_price']
        print(f"\n💳 Adding your credit cards saved an extra ${extra_savings:.2f}!")
        print("   Credit card rewards are OPTIONAL - only YOUR cards are used.")
        
    asyncio.run(main())
