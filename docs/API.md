# Net Price Finder API Documentation

> **Version:** 0.5.0  
> **Base URL:** `http://localhost:8000`

## Overview

The Net Price Finder API provides endpoints for calculating the TRUE net price of products after all savings stack: cashback, coupons, and credit card rewards.

---

## Table of Contents

1. [Authentication](#authentication)
2. [Quick Start](#quick-start)
3. [Endpoints](#endpoints)
   - [Health Check](#health-check)
   - [Quick Price Calculation](#quick-price-calculation)
   - [Find Best Price](#find-best-price)
   - [Cashback Rates](#cashback-rates)
   - [Card Wallet Management](#card-wallet-management)
4. [Data Models](#data-models)
5. [Error Handling](#error-handling)
6. [Examples](#examples)

---

## Authentication

Currently, the API does not require authentication for local use. In production deployments, implement API key or JWT authentication.

---

## Quick Start

### Calculate Net Price
```bash
curl -X POST http://localhost:8000/api/v1/quick-price \
  -H "Content-Type: application/json" \
  -d '{
    "product_price": 100.00,
    "cashback_percent": 5.0,
    "card_reward_percent": 3.0,
    "coupon_discount": 10.00,
    "tax_rate": 0.0825,
    "shipping": 0.00
  }'
```

### Response
```json
{
  "product_price": 100.00,
  "coupon_discount": 10.00,
  "tax": 8.25,
  "shipping": 0.00,
  "gross_total": 98.25,
  "cashback": 4.91,
  "card_rewards": 2.95,
  "net_price": 90.39,
  "total_savings": 17.86,
  "savings_percent": 17.86
}
```

---

## Endpoints

### Health Check

Check if the API is running and healthy.

**Endpoint:** `GET /health`

**Response:**
```json
{
  "status": "healthy",
  "version": "0.5.0",
  "services": {
    "optimizer": "ready",
    "cashback_monitor": "ready",
    "card_wallet": "0 cards"
  }
}
```

---

### Quick Price Calculation

Calculate net price instantly without scraping. Use this for real-time calculations when you already know the values.

**Endpoint:** `POST /api/v1/quick-price`

**Request Body:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `product_price` | float | ✅ | - | Original product price (must be > 0) |
| `cashback_percent` | float | ❌ | 0 | Cashback percentage (0-100) |
| `card_reward_percent` | float | ❌ | 0 | Credit card reward percentage (0-100) |
| `coupon_discount` | float | ❌ | 0 | Coupon discount amount in $ |
| `tax_rate` | float | ❌ | 0 | Tax rate as decimal (e.g., 0.0825 for 8.25%) |
| `shipping` | float | ❌ | 0 | Shipping cost |

**Example Request:**
```json
{
  "product_price": 149.99,
  "cashback_percent": 8.0,
  "card_reward_percent": 4.0,
  "coupon_discount": 25.00,
  "tax_rate": 0.0825,
  "shipping": 0.00
}
```

**Response:**
```json
{
  "product_price": 149.99,
  "coupon_discount": 25.00,
  "tax": 12.37,
  "shipping": 0.00,
  "gross_total": 137.36,
  "cashback": 10.99,
  "card_rewards": 5.49,
  "net_price": 120.88,
  "total_savings": 29.11,
  "savings_percent": 19.41
}
```

---

### Find Best Price

Find the TRUE cheapest price for a product URL. This endpoint:
1. Scrapes the product page for price
2. Searches cashback platforms (Rakuten, TopCashback, etc.)
3. Finds applicable coupons
4. Calculates credit card rewards (if user has cards configured)

**Endpoint:** `POST /api/v1/find-best-price`

**Request Body:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | ✅ | - | Product URL or search term |
| `include_cashback` | bool | ❌ | true | Search cashback platforms |
| `include_coupons` | bool | ❌ | true | Search for coupons |

**Example Request:**
```json
{
  "query": "https://nike.com/t/air-max-90-mens-shoes/DH8010-100",
  "include_cashback": true,
  "include_coupons": true
}
```

**Response:**
```json
{
  "product_price": 130.00,
  "retailer": "Nike.com",
  "original_url": "https://nike.com/t/air-max-90-mens-shoes/DH8010-100",
  "coupon_code": "SAVE20",
  "coupon_discount": 26.00,
  "tax": 8.58,
  "shipping": 0.00,
  "gross_total": 112.58,
  "cashback_platform": "Rakuten",
  "cashback_percent": 8.0,
  "cashback_value": 9.01,
  "card_name": "Chase Sapphire Preferred",
  "card_reward_percent": 3.0,
  "card_reward_value": 3.38,
  "net_price": 100.19,
  "total_savings": 29.81,
  "savings_percent": 22.93,
  "timestamp": "2026-01-03T14:30:00Z"
}
```

---

### Cashback Rates

Get current cashback rates for a merchant across all platforms.

**Endpoint:** `POST /api/v1/cashback-rates`

**Request Body:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `merchant` | string | ✅ | Merchant name (e.g., "Nike", "Amazon") |

**Example Request:**
```json
{
  "merchant": "Nike"
}
```

**Response:**
```json
{
  "merchant": "Nike",
  "best_platform": "Rakuten",
  "best_rate": 8.0,
  "rates": [
    {
      "platform": "Rakuten",
      "rate": 8.0,
      "type": "percent",
      "terms": "Excludes gift cards"
    },
    {
      "platform": "TopCashback",
      "rate": 6.0,
      "type": "percent",
      "terms": "New customers only"
    },
    {
      "platform": "BeFrugal",
      "rate": 5.5,
      "type": "percent",
      "terms": null
    }
  ]
}
```

---

### Card Wallet Management

Manage your credit card wallet. Cards are used to calculate optimal rewards.

#### Get Wallet

**Endpoint:** `GET /api/v1/wallet`

**Response:**
```json
{
  "cards": [
    {
      "name": "Chase Sapphire Preferred",
      "issuer": "Chase",
      "base_rate": 1.0,
      "bonus_categories": [
        {"category": "Dining", "rate": 3.0},
        {"category": "Travel", "rate": 2.0}
      ]
    }
  ],
  "card_count": 1
}
```

#### Get Popular Cards

Get list of pre-built popular cards that can be added to wallet.

**Endpoint:** `GET /api/v1/popular-cards`

**Response:**
```json
{
  "cards": [
    {
      "name": "Chase Sapphire Preferred",
      "issuer": "Chase",
      "base_rate": 1.0,
      "highlights": ["3x Dining", "3x Travel", "2x Streaming"]
    },
    {
      "name": "Amex Gold",
      "issuer": "American Express",
      "base_rate": 1.0,
      "highlights": ["4x Restaurants", "4x Groceries", "3x Flights"]
    }
  ]
}
```

#### Add Popular Card

Add a pre-built popular card to your wallet.

**Endpoint:** `POST /api/v1/wallet/add-popular/{card_name}`

**Example:**
```bash
curl -X POST http://localhost:8000/api/v1/wallet/add-popular/Chase%20Sapphire%20Preferred
```

**Response:**
```json
{
  "status": "added",
  "card": "Chase Sapphire Preferred",
  "total_cards": 1
}
```

#### Add Custom Card

Add a custom card with your own bonus categories.

**Endpoint:** `POST /api/v1/wallet/add`

**Request Body:**
```json
{
  "name": "My Credit Card",
  "issuer": "My Bank",
  "base_rate": 1.5,
  "bonus_categories": [
    {"category": "Dining", "rate": 4.0},
    {"category": "Gas", "rate": 3.0}
  ]
}
```

**Response:**
```json
{
  "status": "added",
  "card": "My Credit Card",
  "total_cards": 2
}
```

#### Remove Card

Remove a card from your wallet.

**Endpoint:** `DELETE /api/v1/wallet/{card_name}`

**Example:**
```bash
curl -X DELETE http://localhost:8000/api/v1/wallet/Chase%20Sapphire%20Preferred
```

**Response:**
```json
{
  "status": "removed",
  "card": "Chase Sapphire Preferred",
  "total_cards": 0
}
```

---

## Data Models

### QuickPriceRequest
```typescript
interface QuickPriceRequest {
  product_price: number;      // Required, > 0
  cashback_percent?: number;  // 0-100, default 0
  card_reward_percent?: number; // 0-100, default 0
  coupon_discount?: number;   // >= 0, default 0
  tax_rate?: number;          // 0-1, default 0
  shipping?: number;          // >= 0, default 0
}
```

### SavingsResponse
```typescript
interface SavingsResponse {
  product_price: number;
  retailer: string;
  original_url: string;
  coupon_code: string | null;
  coupon_discount: number;
  tax: number;
  shipping: number;
  gross_total: number;
  cashback_platform: string | null;
  cashback_percent: number;
  cashback_value: number;
  card_name: string | null;
  card_reward_percent: number;
  card_reward_value: number;
  net_price: number;
  total_savings: number;
  savings_percent: number;
  timestamp: string;  // ISO 8601 datetime
}
```

### CardInfo
```typescript
interface CardInfo {
  name: string;
  issuer: string;
  base_rate: number;
  bonus_categories?: BonusCategory[];
}

interface BonusCategory {
  category: string;
  rate: number;
}
```

---

## Error Handling

### HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request - Invalid input |
| 404 | Not Found - Resource doesn't exist |
| 422 | Validation Error - Invalid request body |
| 500 | Internal Server Error |

### Error Response Format
```json
{
  "detail": "Error message describing what went wrong"
}
```

### Validation Error Format
```json
{
  "detail": [
    {
      "loc": ["body", "product_price"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## Examples

### Example 1: Nike Shoe Purchase

Calculate the net price for a Nike shoe purchase with Rakuten cashback and Chase Sapphire:

```bash
curl -X POST http://localhost:8000/api/v1/quick-price \
  -H "Content-Type: application/json" \
  -d '{
    "product_price": 120.00,
    "cashback_percent": 8.0,
    "card_reward_percent": 3.0,
    "coupon_discount": 18.00,
    "tax_rate": 0.0825,
    "shipping": 0.00
  }'
```

**Result:**
- Original: $120.00
- After coupon: $102.00
- After tax: $111.90
- After cashback (-$8.95): $102.95
- After card rewards (-$3.36): **$99.59 NET**
- **Total Savings: $20.41 (17%)**

### Example 2: Amazon Prime Purchase

Calculate using Amazon Prime Visa (5% back on Amazon):

```bash
curl -X POST http://localhost:8000/api/v1/quick-price \
  -H "Content-Type: application/json" \
  -d '{
    "product_price": 79.99,
    "cashback_percent": 1.0,
    "card_reward_percent": 5.0,
    "coupon_discount": 0,
    "tax_rate": 0.0825,
    "shipping": 0.00
  }'
```

### Example 3: Set Up Card Wallet

```bash
# Add Chase Sapphire Preferred
curl -X POST http://localhost:8000/api/v1/wallet/add-popular/Chase%20Sapphire%20Preferred

# Add Amex Gold
curl -X POST http://localhost:8000/api/v1/wallet/add-popular/Amex%20Gold

# Check wallet
curl http://localhost:8000/api/v1/wallet
```

---

## Rate Limits

Currently no rate limits are enforced for local deployment. In production:
- `/api/v1/quick-price`: 100 requests/minute
- `/api/v1/find-best-price`: 10 requests/minute (involves scraping)
- `/api/v1/cashback-rates`: 30 requests/minute

---

## OpenAPI / Swagger

Interactive API documentation is available at:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI JSON:** `http://localhost:8000/openapi.json`

---

## Changelog

### v0.5.0 (2026-01-03)
- Initial API release
- Quick price calculation endpoint
- Card wallet management
- Cashback rates lookup
- Find best price endpoint (with scraping)
