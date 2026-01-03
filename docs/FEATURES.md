# Net Price Finder - Features Documentation

> **Version:** 0.5.0  
> **Last Updated:** 2026-01-03

## Overview

Net Price Finder helps you discover the TRUE cheapest price for any product by stacking all available savings:

1. **Cashback** from portals (Rakuten, TopCashback, Honey, etc.)
2. **Coupons** automatically discovered
3. **Credit Card Rewards** (optional - only YOUR cards)

---

## Table of Contents

1. [Core Features](#core-features)
2. [Net Price Optimizer](#net-price-optimizer)
3. [Cashback Monitor](#cashback-monitor)
4. [Credit Card Rewards](#credit-card-rewards)
5. [Frontend Dashboard](#frontend-dashboard)
6. [Vision Parser](#vision-parser)
7. [Architecture](#architecture)

---

## Core Features

### 🔍 Product Price Lookup

Paste any product URL and we'll:
- Extract the current price
- Find applicable coupons
- Check all cashback platforms
- Calculate credit card rewards
- Show you the TRUE net price

**Supported Retailers:**
- Amazon
- Nike
- Target
- Walmart
- Best Buy
- Nordstrom
- Macy's
- Sephora
- And 20+ more...

### 💰 Net Price Calculation

Our formula:
```
Net Price = (Product - Coupon + Tax + Shipping) - Cashback - Card Rewards
```

**Example:**
| Line Item | Amount |
|-----------|--------|
| Product Price | $120.00 |
| Coupon (SAVE15) | -$18.00 |
| Tax (8.25%) | +$8.42 |
| Shipping | FREE |
| **Subtotal** | **$110.42** |
| Rakuten (8%) | -$8.83 |
| Chase Sapphire (3x) | -$3.31 |
| **NET PRICE** | **$98.28** |
| **Total Savings** | **$21.72 (18.1%)** |

---

## Net Price Optimizer

**Location:** `intelligence-core/optimizer/net_price.py`

The core intelligence module that calculates the TRUE net price.

### Features

1. **Multi-Retailer Support** - Recognizes 30+ major retailers
2. **MCC Code Mapping** - Maps retailers to Merchant Category Codes for accurate card rewards
3. **Coupon Discovery** - Scrapes coupons from RetailMeNot, Honey, vendor sites
4. **Cashback Comparison** - Compares rates across 5 platforms
5. **Card Optimization** - Recommends the best card from your wallet

### Usage

```python
from optimizer.net_price import NetPriceOptimizer, calculate_net_price

# Quick calculation (no scraping)
result = calculate_net_price(
    product_price=100.00,
    cashback_percent=5.0,
    card_reward_percent=3.0,
    coupon_discount=10.00,
    tax_rate=0.0825,
    shipping=0.00
)
print(f"Net Price: ${result['net_price']:.2f}")

# Full optimization (with scraping)
async with NetPriceOptimizer(card_wallet=my_wallet) as optimizer:
    result = await optimizer.optimize("https://nike.com/product/...")
```

### Key Classes

| Class | Purpose |
|-------|---------|
| `NetPriceOptimizer` | Main optimizer with scraping |
| `ProductScraper` | Extracts price from product pages |
| `CouponFinder` | Discovers applicable coupons |
| `SavingsBreakdown` | Data model for results |
| `RetailerOption` | Represents a retailer with pricing |

---

## Cashback Monitor

**Location:** `intelligence-core/cashback/monitor.py`

Scrapes and compares cashback rates across multiple platforms.

### Supported Platforms

| Platform | Typical Rates | Notes |
|----------|---------------|-------|
| **Rakuten** | 1-15% | Most popular, reliable |
| **TopCashback** | 1-20% | Often highest rates |
| **Honey** | 1-10% | Gold rewards system |
| **BeFrugal** | 1-15% | $5 signup bonus |
| **Swagbucks** | 1-10% | SB points (1 SB = $0.01) |

### Features

1. **Parallel Scraping** - Checks all platforms simultaneously
2. **Rate Normalization** - Converts points/miles to cash value
3. **Caching** - 6-hour TTL to reduce scraping
4. **Best Rate Finding** - Automatically selects highest rate

### Usage

```python
from cashback.monitor import CashbackMonitor

async with CashbackMonitor() as monitor:
    result = await monitor.get_best_cashback("Nike")
    
    print(f"Best Platform: {result.best_offer.platform}")
    print(f"Best Rate: {result.best_rate}%")
    
    for offer in result.offers:
        print(f"  {offer.platform}: {offer.rate}%")
```

---

## Credit Card Rewards

**Location:** `intelligence-core/rewards/schema.py`

Manages credit card reward optimization.

### Key Principle

> **Credit card rewards are OPTIONAL.** We only use YOUR cards.

If you don't add any cards to your wallet, we'll still show you:
- Cashback opportunities
- Available coupons
- The net price (without card rewards)

### Pre-Built Popular Cards

| Card | Key Benefits |
|------|--------------|
| **Chase Sapphire Preferred** | 3x Dining, 3x Travel, 2x Streaming |
| **Amex Gold** | 4x Restaurants, 4x Groceries, 3x Flights |
| **Citi Double Cash** | 2% on everything |
| **Chase Freedom Flex** | 5% Rotating, 3x Dining, 3x Drugstores |
| **Discover it** | 5% Rotating categories |
| **Amazon Prime Visa** | 5% Amazon, 2% Restaurants |

### Adding Your Cards

**Via API:**
```bash
# Add a popular card
curl -X POST http://localhost:8000/api/v1/wallet/add-popular/Chase%20Sapphire%20Preferred

# Add a custom card
curl -X POST http://localhost:8000/api/v1/wallet/add \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Card",
    "issuer": "My Bank",
    "base_rate": 1.5,
    "bonus_categories": [
      {"category": "Dining", "rate": 4.0}
    ]
  }'
```

**Via Dashboard:**
1. Click "My Cards" in the header
2. Browse popular cards
3. Click "Add" on any card you have
4. Cards persist for the session

### How Card Optimization Works

1. We identify the **MCC (Merchant Category Code)** for the retailer
2. We check each card's bonus categories against that MCC
3. We recommend the card with the highest reward rate
4. We calculate the reward value in dollars

**Example:**
```
Retailer: Nike.com
MCC: 5651 (Family Clothing Stores)

Card 1: Amex Gold - 1x on Clothing = 1%
Card 2: Chase Freedom Flex - 1x base = 1%
Card 3: Citi Double Cash - 2% on everything = 2%

Winner: Citi Double Cash (2%)
```

---

## Frontend Dashboard

**Location:** `app-frontend/main.py`

NiceGUI-powered dashboard for interacting with the system.

### Pages

| Route | Description |
|-------|-------------|
| `/` | Main search page with hero and calculator |
| `/results` | Savings breakdown display |
| `/cards` | Card wallet management |
| `/settings` | Configuration options |
| `/health` | Health check endpoint |

### Features

1. **Search Hero** - Paste product URLs for instant analysis
2. **Quick Calculator** - Calculate net price with known values
3. **Results Display** - Beautiful breakdown of all savings
4. **Card Wallet** - Add/remove your credit cards
5. **Dark Mode** - Easy on the eyes

### Screenshots

```
┌─────────────────────────────────────────────────────────────┐
│ 💰 Net Price Finder     Find the TRUE cheapest price        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│        🔍 Paste a product link                              │
│    We'll find cashback, coupons, and the best card          │
│                                                             │
│    ┌─────────────────────────────────────────────────────┐  │
│    │ https://nike.com/t/air-max-90...                    │  │
│    └─────────────────────────────────────────────────────┘  │
│                        [ Find Best Price ]                  │
│                                                             │
│    💳 Add your cards    🏷️ Auto-find coupons    💵 5+ sites │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  🧮 Quick Calculator                                        │
│  Price: $100   Cashback: 5%   Coupon: $10   Card: 0%       │
│                                                             │
│  Net Price: $XX.XX    [ Calculate ]                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Vision Parser

**Location:** `intelligence-core/vision/parser.py`

Extracts transaction data from PDFs and receipts using vision AI.

### Capabilities

1. **PDF Statements** - Bank and credit card statements
2. **Receipts** - Paper receipts as images
3. **Screenshots** - Transaction screenshots

### How It Works

1. **PDF → Image** - Convert PDF pages to high-resolution images
2. **Vision AI** - Use Ollama's LLaVA model to "read" the document
3. **Extraction** - Pull out date, description, amount for each transaction
4. **MCC Enrichment** - Categorize merchants automatically
5. **Validation** - Pydantic schemas ensure data integrity

### Usage

```python
from vision.parser import VisionParser

async with VisionParser() as parser:
    result = await parser.parse_document("statement.pdf")
    
    for tx in result.transactions:
        print(f"{tx.date}: {tx.description} - ${tx.amount}")
```

---

## Architecture

### System Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     User Browser (:8080)                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    app-frontend (NiceGUI)                    │
│              WebSocket Server + Dashboard UI                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  intelligence-core/api                       │
│                 FastAPI Server (:8000)                       │
│   ┌──────────────┬──────────────┬──────────────────────┐    │
│   │  optimizer/  │   rewards/   │      cashback/       │    │
│   │  net_price   │   schema     │      monitor         │    │
│   └──────────────┴──────────────┴──────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  scraper-engine │ │intelligence-core│ │   firefly-iii   │
│   (Playwright)  │ │    (Ollama)     │ │   (Ledger DB)   │
│   GPU: WebGL    │ │   GPU: CUDA     │ │                 │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Docker Services

| Service | Port | Purpose |
|---------|------|---------|
| app-frontend | 8080 | User dashboard |
| api-server | 8000 | REST API |
| scraper-engine | 5000 | Visual scraper |
| intelligence-core | 11434 | Ollama LLM |
| firefly-iii | 8081 | Financial ledger |
| redis | 6379 | Message bus |
| mariadb | 3306 | Database |

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | localhost | Redis server host |
| `REDIS_PORT` | 6379 | Redis server port |
| `OLLAMA_API_URL` | http://ollama:11434 | Ollama API endpoint |
| `SCRAPER_API_URL` | http://scraper-engine:5000 | Scraper endpoint |
| `API_URL` | http://localhost:8000 | API server URL |
| `FIREFLY_API_URL` | http://firefly:8080 | Firefly III endpoint |

### Tax Rates

Configure your default tax rate in the Settings page. Common rates:
- California: 7.25-10.25%
- Texas: 6.25-8.25%
- New York: 4-8.875%
- No tax: Delaware, Montana, Oregon, NH

---

## Best Practices

### Maximizing Savings

1. **Always check cashback first** - Rates change daily
2. **Stack coupons with cashback** - They usually work together
3. **Use the right card** - Category bonuses can be 3-5x better
4. **Time your purchases** - Holiday sales + cashback = max savings

### Privacy

- All data stays on YOUR machine
- No browser extensions tracking you
- No data sold to third parties
- You control your card information

---

## Troubleshooting

### Common Issues

**Q: Cashback rates not loading**  
A: The scraper may be blocked. Try again in a few minutes.

**Q: Card rewards showing 0%**  
A: Make sure you've added cards to your wallet.

**Q: Price not detected**  
A: Some sites have anti-scraping measures. Try a different retailer.

### Getting Help

- Check the logs: `docker compose logs -f`
- API docs: `http://localhost:8000/docs`
- GitHub Issues: [Report a bug](https://github.com)

---

## Changelog

See [ROADMAP.md](../ROADMAP.md) for full version history.
