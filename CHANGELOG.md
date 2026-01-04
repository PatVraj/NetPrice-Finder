# SSIP Changelog

> **Detailed Version History & Change Tracking**
> 
> **Structure:** Version (high-level) → Branch (feature work) → Commit (atomic changes)
> 
> For current work and future planning, see [ROADMAP.md](ROADMAP.md)

---

## 📊 Version History

---

## 🏷️ v0.8.0 – Cross-Retailer Comparison, QA & UX Polish
**Status:** 🔄 In Progress  
**Started:** 2026-01-04

### Branch: `feature/v0.8-bugfixes`
**Created:** 2026-01-04  
**Merged:** Open  
**Purpose:** Bug fixes and comprehensive test coverage for QA

#### Commits:

| Commit | Date | Files Changed | Description |
|--------|------|---------------|-------------|
| `0364149` | 2026-01-04 | 1 file | Fix `user_tax_rate` AttributeError in User class |
| `6aaba8c` | 2026-01-04 | 4 files | Bug fixes and test suites for v0.8.0 QA |
| `f7fc989` | 2026-01-04 | 1 file | Update roadmap with bug fixes and test suites |

#### Session: 2026-01-04 – Bug Fixes & Test Suite Development

**Files Created:**
- `app-frontend/tests/test_input_validation.py` – 28 tests for email, password, query, tax rate, location validation
- `intelligence-core/tests/test_error_handling.py` – 36 tests for API error handling and edge cases

**Files Modified:**
- `app-frontend/database.py` – Added null checks to `get_user_by_email()` and `authenticate_user()`
- `app-frontend/main.py` – Added `tax_rate` and `location` fields to User dataclass
- `intelligence-core/api/server.py` – Fixed POPULAR_CARDS iteration, CardInfo validation, health endpoint

**Bugs Fixed:**
- `authenticate_user` crashes on `None` email → Added null check
- `get_user_by_email` crashes on `None` email → Added null check  
- `POPULAR_CARDS` iteration fails (factory vs object) → Fixed to call factory functions
- `CardInfo` allows empty name / negative rate → Added Pydantic validation
- `/health` crashes if lifespan not run → Graceful handling of missing state

**Test Coverage Added:**
- Input validation tests: Email, password, product query, tax rate, location
- API error handling: Malformed requests, invalid data, wallet operations
- Authentication edge cases: Null values, timing attack resistance

---

## 🏷️ v0.7.0 – Data Persistence & User Experience
**Status:** ✅ Complete  
**Started:** 2026-01-03  
**Completed:** 2026-01-04

### Branch: `feature/data-persistence`
**Created:** 2026-01-03  
**Merged:** Open  
**Purpose:** Persistent storage for users, card wallets, and search history

#### Commits:

| Commit | Date | Files Changed | Description |
|--------|------|---------------|-------------|
| `5592a8d` | 2026-01-03 | 7 files | SQLite user database with full persistence |
| `dffddff` | 2026-01-03 | 4 files | RetailerIntelligence integration for cashback caching |
| `4b41f00` | 2026-01-03 | 5 files | Code review fixes: security, tests, refactoring |

#### Session: 2026-01-03 – Data Persistence Implementation

**Files Created:**
- `app-frontend/database.py` – SQLite database layer with UserDatabase class
- `app-frontend/tests/__init__.py` – Test module initialization
- `app-frontend/tests/test_database.py` – 30+ test cases for database operations

**Files Modified:**
- `app-frontend/main.py` – Integrated SQLite database for all user operations
- `app-frontend/requirements.txt` – Added bcrypt for secure password hashing
- `docker-compose.yml` – Added USER_DB_PATH and DEMO_MODE environment variables

**Key Features Implemented:**
1. **SQLite User Database:** Full schema with users, user_cards, search_history tables
2. **Password Hashing:** bcrypt with SHA256 fallback for security
3. **Card Wallet Persistence:** Users' credit cards saved to database
4. **Search History Tracking:** Every search saved with results for analytics
5. **User Settings:** Tax rate and location preferences persist
6. **Admin Dashboard:** Now shows real user counts from database
7. **Settings Page Enhanced:** Shows account info, all 50 US states, savings stats

**Database Schema:**
```sql
users (id, email, password_hash, is_admin, tax_rate, location, created_at, updated_at)
user_cards (id, user_id, card_id, name, issuer, base_rate, bonus_categories, is_custom)
search_history (id, user_id, product_url, product_name, retailer, product_price, net_price, total_savings, best_cashback_platform, best_cashback_rate, searched_at)
```

**Test Coverage:**
- Password hashing/verification (5 tests)
- User CRUD operations (12 tests)
- Card wallet management (7 tests)
- Search history tracking (6 tests)
- Data persistence across reconnects (2 tests)

#### Session: 2026-01-03 – RetailerIntelligence Integration

**Files Modified:**
- `intelligence-core/cashback/monitor.py` – Cache-first lookup via RetailerIntelligence, stores results after scraping
- `intelligence-core/optimizer/net_price.py` – Passes cache metadata through optimization result
- `intelligence-core/api/server.py` – API response includes cache status (from_cache, last_updated)
- `app-frontend/main.py` – UI shows "Rates updated X hours ago" in Cashback Comparison section

**Key Features Implemented:**
1. **Cache-First Lookup:** CashbackMonitor checks RetailerIntelligence SQLite/Redis cache before scraping
2. **Persistent Storage:** Fresh scrape results stored to SQLite database and warmed in Redis
3. **Cache Metadata:** API response includes `cashback_from_cache` and `cashback_last_updated` fields
4. **UI Transparency:** Users see when cashback rates were last updated (fresh vs cached)
5. **Tier-Based TTL:** Major retailers (Amazon, Target) = 4h, standard = 12h, minor = 24h

**Integration Flow:**
```
1. User searches for product
2. CashbackMonitor.find_best_cashback() called
3. Check RetailerIntelligence cache (Redis → SQLite)
4. If fresh: return cached data with metadata
5. If stale/missing: scrape all 5 platforms
6. Store results to SQLite and warm Redis
7. Return with cashback_from_cache=false, cashback_last_updated="Just scraped"
```

#### Session: 2026-01-03 – Code Review Fixes

**Files Modified:**
- `app-frontend/database.py` – Security fixes and helper refactoring
- `app-frontend/main.py` – Tax rate clearing fix, state.db None guards
- `app-frontend/tests/test_database.py` – Additional test coverage
- `intelligence-core/cashback/monitor.py` – Serialization fix and helper methods

**Security Fixes:**
1. **DEMO_MODE flag:** `verify_password` now only accepts `$demo$` hashes when `DEMO_MODE` is enabled
2. **SQL injection prevention:** `update_user_settings` uses parameterized queries instead of string concatenation
3. **state.db guards:** Protected pages (admin, settings, cards) check for `state.db` existence

**Bug Fixes:**
1. **Tax rate clearing:** Added `clear_tax_rate=True` parameter to properly set tax_rate to NULL
2. **Cache serialization:** Replaced `__dict__` with proper `to_dict()` serialization

**Test Coverage Added:**
- `test_verify_password_malformed_sha256_hash` – Handles malformed/missing hash parts
- `test_verify_password_malformed_bcrypt_hash` – Handles truncated/corrupted bcrypt
- `test_verify_password_unknown_format` – Rejects unrecognized hash formats
- `test_verify_demo_password_with_demo_mode` – Verifies DEMO_MODE gating
- `test_verify_demo_password_without_demo_mode` – Ensures demo bypass fails in production
- `test_get_user_savings_stats_empty_history` – Returns safe defaults for empty history
- `test_get_user_savings_stats_nonexistent_user` – Handles missing user gracefully
- `test_get_user_database_singleton_returns_same_instance` – Validates singleton pattern
- `test_get_user_database_uses_env_path` – Validates USER_DB_PATH environment usage

**Refactoring:**
1. **database.py helpers:** Added `_row_to_user()`, `_row_to_card()`, `_serialize_bonus_categories()`
2. **MerchantCashback:** Added `set_cache_metadata()` method for cleaner cache handling
3. **CashbackMonitor helpers:** Extracted `_get_from_intelligence_cache()`, `_scrape_all_platforms()`, `_convert_stored_offer()`
4. **find_best_cashback:** Reduced complexity from 100+ lines to ~25 lines using helpers

#### Tasks Completed:

| Task | Status | Priority |
|------|--------|----------|
| SQLite database for user accounts | ✅ | 🔴 Critical |
| Persist card wallet per user | ✅ | 🔴 Critical |
| Search history storage | ✅ | 🟡 Medium |
| Integrate RetailerIntelligence with frontend | ✅ | 🟡 Medium |
| User settings persistence (tax rate, location) | ✅ | 🟢 Low |

**Milestone:** User data persists across container restarts

---

## 🏷️ v0.6.0 – Frontend Integration, Testing & Documentation
**Status:** ✅ Complete  
**Started:** 2026-01-03  
**Completed:** 2026-01-04

### Branch: `feature/phase4-sovereign-features`
**Created:** 2026-01-04  
**Merged:** Open  
**Purpose:** Net Price Finder - find TRUE cheapest price after all savings stack

#### Commits:

| Commit | Date | Files Changed | Description |
|--------|------|---------------|-------------|
| `85d51e7` | 2026-01-04 | 8 files | Fix false positive cashback + auto tax detection |
| `bbf7279` | 2026-01-04 | 3 files | Vision Parser for PDFs + MCC enrichment |
| `8e5c8d6` | 2026-01-04 | 4 files | Credit Card Reward Schema + Cashback Monitor |
| `43c97c2` | 2026-01-04 | 4 files | Net Price Optimizer - core intelligence |
| `19d8ff0` | 2026-01-04 | 1 file | Clarify credit card rewards are optional |
| `642c106` | 2026-01-04 | 1 file | Update roadmap with Phase 4 details |
| `866c0d2` | 2026-01-03 | 3 files | Frontend integration with Net Price Optimizer |
| `4ade820` | 2026-01-03 | 6 files | Comprehensive test suite and API documentation |

#### Files Created (Phase 4 - Sovereign Features):
- `intelligence-core/vision/parser.py` – PDF/receipt parsing with LLaVA
- `intelligence-core/vision/__init__.py` – Module exports
- `intelligence-core/rewards/schema.py` – Credit card reward optimization
- `intelligence-core/rewards/__init__.py` – Module exports
- `intelligence-core/cashback/monitor.py` – Multi-platform cashback scraping
- `intelligence-core/cashback/__init__.py` – Module exports
- `intelligence-core/optimizer/net_price.py` – Net Price Optimizer (core)
- `intelligence-core/optimizer/__init__.py` – Module exports
- `intelligence-core/tax/location.py` – Auto tax detection via IP geolocation
- `intelligence-core/tax/__init__.py` – Module exports

#### Files Created (Phase 5 - Frontend Integration):
- `intelligence-core/api/server.py` – FastAPI server for optimizer endpoints
- `intelligence-core/api/__init__.py` – Module exports

#### Files Created (Phase 6 - Testing & Documentation):
- `intelligence-core/tests/__init__.py` – Test suite initialization
- `intelligence-core/tests/test_net_price.py` – 25+ test cases for optimizer
- `intelligence-core/tests/test_rewards.py` – 20+ test cases for card rewards
- `intelligence-core/tests/test_api.py` – 25+ test cases for API endpoints
- `docs/API.md` – Comprehensive API endpoint documentation
- `docs/FEATURES.md` – User guide and architecture documentation

#### Files Modified:
- `app-frontend/main.py` – Complete rewrite with Net Price Finder UI
- `intelligence-core/optimizer/__init__.py` – Module exports

#### Key Design Decisions:
1. **Credit card rewards are OPTIONAL** – Only user's actual cards are used
2. **Cashback stacking** – Compares 5 platforms: Rakuten, Honey, TopCashback, BeFrugal, Swagbucks
3. **Coupon finding** – Scrapes coupons from RetailMeNot, Honey, vendor sites
4. **Net price calculation** – Product - Coupon + Tax - Cashback - Card Rewards = TRUE cost

#### Session: 2026-01-04 – Cashback Verification & Tax Detection

**Issues Fixed:**
- 🐛 TopCashback scraper returning false positives (2% for non-existent merchants)
- 🐛 Hardcoded cashback rates removed in favor of live scraping
- ✨ Added auto tax detection based on user's IP location

**Changes Made:**
1. **TopCashback Scraper Rewrite:**
   - Uses search API (`/ajax/merchant/search`) for reliable data
   - Added `_is_merchant_match()` to verify merchant name matches
   - Added `_is_valid_merchant_page()` to detect 404/error pages
   - Confidence scores: 0.95 (API) vs 0.85 (page scrape)
   - Removed browser fallback that caused false positives

2. **Auto Tax Detection:**
   - Created `intelligence-core/tax/location.py` with `TaxCalculator`
   - IP geolocation via ip-api.com (free, no API key)
   - Complete US state sales tax database (50 states + DC)
   - 24-hour location caching to reduce API calls
   - Returns location-aware tax rate in API response

3. **Frontend Updates:**
   - Added `product_name` display from LLM extraction
   - Shows tax as "Tax (California) @ 8.85%"
   - Improved progress feedback during optimization

**Files Modified:**
- `intelligence-core/cashback/monitor.py` – Rewrote TopCashback scraper
- `intelligence-core/api/server.py` – Added tax detection to API
- `app-frontend/main.py` – Added tax location display

---

#### Session: 2026-01-04 – Retailer Intelligence System

**Commit:** `1290131`  
**Feature:** Persistent caching system for major retailers with intelligent savings strategies

**Design Document:** `docs/RETAILER_INTELLIGENCE_DESIGN.md`

**Problem Solved:**
- 🐛 Re-scraping cashback rates every search was inefficient
- 🐛 No persistent storage for promo codes with context
- 🐛 Only keeping "best" offer lost stacking opportunities (e.g., PayPal + CC combo)
- ✨ Added intelligent strategy calculation with stacking rules

**Architecture Decisions:**
1. **Hybrid Storage:** Redis (hot cache) + SQLite (persistent)
   - Redis: Fast lookups with tier-based TTL (4h/12h/24h)
   - SQLite: Long-term storage, avoids coupling with Firefly III's MariaDB
2. **Tier System:** Major retailers (60+) get priority refresh
3. **Store ALL Offers:** Keep every cashback/promo for intelligent decision-making
4. **Stacking Rules:** Defined which savings sources can combine

**Files Created:**
| File | Description |
|------|-------------|
| `docs/RETAILER_INTELLIGENCE_DESIGN.md` | Full architecture specification |
| `intelligence-core/retailer/__init__.py` | Module exports |
| `intelligence-core/retailer/models.py` | Data classes (Retailer, StoredCashbackOffer, StoredPromoCode, PaymentBonus, SavingsStrategy, etc.) |
| `intelligence-core/retailer/database.py` | SQLite persistence layer with full CRUD |
| `intelligence-core/retailer/cache.py` | Redis hot cache with TTL management |
| `intelligence-core/retailer/strategy.py` | Stacking rules and strategy calculation |
| `intelligence-core/retailer/intelligence.py` | Main RetailerIntelligence class |

**Files Modified:**
| File | Changes |
|------|---------|
| `intelligence-core/cashback/monitor.py` | Added optional `intelligence` parameter |
| `intelligence-core/optimizer/net_price.py` | Added optional `intelligence` parameter |
| `intelligence-core/api/server.py` | Added 5 new endpoints for retailer intelligence |
| `docker-compose.yml` | Added `RETAILER_DB_PATH` env var and `intelligence_data` volume |

**New API Endpoints:**
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/retailer/{name}/deals` | GET | Get all cached deals for a retailer |
| `/retailer/{name}/strategy` | GET | Calculate optimal savings strategy |
| `/retailer/{name}/refresh` | POST | Force refresh retailer data |
| `/intelligence/stats` | GET | Get cache and database statistics |
| `/intelligence/stale` | GET | List retailers needing refresh |

**Key Classes:**
- `RetailerIntelligence` – Main unified interface
- `RetailerDatabase` – SQLite operations
- `RetailerCache` – Redis caching
- `StrategyCalculator` – Stacking rules engine

**Stacking Rules Example:**
```python
# Conflicts (can't stack)
Rakuten ↔ TopCashback ↔ Honey Gold ↔ BeFrugal ↔ Swagbucks

# Can Stack
Cashback + Store Coupon + Credit Card + PayPal/Amex Offers
```

**Milestone:** 70+ test cases and full API/features documentation

---

## 🏷️ v0.5.0 – Sovereign Features (Core Intelligence)
**Status:** ✅ Complete  
**Started:** 2026-01-03  
**Completed:** 2026-01-04

### Features Implemented:
- Vision Parser for PDF statements
- MCC enrichment pipeline
- Credit Card Reward Schema system
- Net Price Optimizer
- Cashback Monitor scraper

**Milestone:** Full sovereign financial intelligence operational

---

## 🏷️ v0.4.0 – Brain & Memory (LLM + Database)
**Status:** ✅ Complete  
**Started:** 2026-01-03  
**Completed:** 2026-01-03

### Features Implemented:
- Ollama container with Llama 3
- Semantic router function calling
- Firefly III + MariaDB deployment
- Python wrapper for Firefly API
- Intent classification prompts

**Milestone:** User query routes correctly to scraper or ledger

---

## 🏷️ v0.3.0 – Eyes (Visual Browser Engine)
**Status:** ✅ Complete  
**Started:** 2026-01-03  
**Completed:** 2026-01-03

### Branch: `feature/ongoing-development`
**Created:** 2026-01-05  
**Merged:** Open  
**Purpose:** Cashback scraper improvements and UI transparency fixes

#### Commits:

| Commit | Date | Files Changed | Description |
|--------|------|---------------|-------------|
| `b5d9675` | 2026-01-05 | 1 file | Add responsive UI design for all screen sizes |
| `946ba91` | 2026-01-05 | 1 file | Modern UI refactor with auth and admin dashboard |
| `10fae56` | 2026-01-05 | 9 files | Remove promo code functionality entirely |
| `8169060` | 2026-01-03 | 4 files | Improve UI progress logs and update remaining scrapers |
| `608d808` | 2026-01-03 | 4 files | Add descriptive logging for backend progress |
| `4ca4219` | 2026-01-03 | 2 files | Fix cashback offers transparency in UI |
| `33fa32e` | 2026-01-03 | 2 files | Fix false positive matching in scrapers |
| `0697291` | 2026-01-03 | 2 files | Add search page scraping strategy |
| `c40a561` | 2026-01-03 | 2 files | Add slug overrides for Pandora, Ulta, etc. |
| `1d78394` | 2026-01-03 | 6 files | Modularize cashback scrapers into package |

#### Session: 2026-01-05 – Remove Promo Code Functionality

**Commit:** `10fae56`  
**Analysis:** Promo codes from cashback sites (Rakuten, TopCashback, etc.) are not real promo codes – they are just marketing "deals" that describe sales (e.g., "Up to 40% off select styles"). These provide no actionable value.

**Changes Made:**
1. **monitor.py:** Removed `PromoCode` dataclass, `promo_codes` field from `MerchantCashback`, `_safe_scrape_promos()` method
2. **All 5 scrapers:** Removed `get_promo_codes()` and `_parse_promo_codes()` methods
3. **net_price.py:** Removed `available_promo_codes` from `OptimizationResult`
4. **server.py:** Removed `PromoCodeInfo`, `PromoSearchResult` classes
5. **main.py (frontend):** Removed promo code UI sections

**Code Removed:** ~700 lines of dead promo code functionality

---

#### Session: 2026-01-05 – Responsive UI Design

**Commit:** `b5d9675`  
**Feature:** Fully responsive design across all screen sizes

**Changes Made:**
1. **Extended CUSTOM_CSS:**
   - Added responsive typography with `clamp()` for fluid sizing
   - Added `.stats-grid` CSS Grid with 1→2→4 column breakpoints
   - Added `.responsive-container` with max-width breakpoints
   - Added mobile nav adjustments, card padding, table overflow

2. **Responsive Navbar:**
   - Fixed positioning at top with z-index
   - Desktop nav links hidden on mobile (`hidden sm:block`)
   - Mobile menu items shown in dropdown

3. **Responsive Pages:**
   - Hero search: `min-h-[calc(100vh-4rem)]`, responsive padding, fluid title
   - Landing page: Responsive padding, smaller text on mobile
   - Results page: Responsive padding, `break-words` for long names
   - Login/Register: Responsive form padding and font sizes
   - Admin dashboard: CSS Grid for stats, responsive tables
   - Cards page: 1-2-3 column grid layout based on screen size
   - Settings page: Responsive padding and spacing
   - Footer: Centered on mobile, justified on desktop

**Key CSS Patterns Applied:**
- Padding: `px-4 sm:px-6 py-6 sm:py-8`
- Font sizes: `text-2xl sm:text-3xl`
- Card padding: `p-4 sm:p-6`
- Card widths: `w-full sm:w-56` for grid items
- Visibility: `hidden sm:block` for desktop-only elements

---

#### Session: 2026-01-05 – Modern UI Refactor with Auth

**Commit:** `946ba91`  
**Feature:** Complete frontend redesign with authentication and admin dashboard

**Changes Made:**
1. **Modern Design System:**
   - Glass morphism effects with backdrop blur
   - Hero gradient background (emerald → slate → indigo)
   - Smooth fade-in animations
   - Stat cards with gradient backgrounds
   - Clean typography with proper spacing

2. **Authentication System:**
   - Login page (`/login`) with email/password
   - Register page (`/register`) with password confirmation
   - Logout functionality via navbar dropdown
   - User session storage with `app.storage.user`
   - SHA256 password hashing
   - Demo admin: `admin@netprice.local` / `admin123`

3. **Admin Dashboard (`/admin`):**
   - Stats cards: Retailers, Cashback Entries, Queries, Users
   - Top Retailers table: Query volume per retailer
   - Platform Status: Live/disabled status per cashback platform
   - Users table: All registered users with admin badges

4. **Removed All Coupon References:**
   - Clean messaging focused on cashback comparison
   - No more "coupon" terminology in UI

**New UI Flow:**
- Unauthenticated users → Landing page with Get Started/Login buttons
- Authenticated users → Hero search with product URL input
- Admin users → Full dashboard access via Admin link in navbar

**New Components:**
- `create_navbar()` – Responsive nav with auth-aware menu
- `create_hero_search()` – Animated search for authenticated users
- `create_landing()` – Landing page for unauthenticated users
- `create_login()` / `create_register()` – Glass-styled auth forms
- `create_admin()` – Full admin dashboard with tables
- `create_results()` – Price breakdown with cashback comparison

---

#### Session: 2026-01-03 – Cashback Scraper Overhaul

**Issues Fixed:**
- 🐛 Pandora cashback not found (wrong URL slugs)
- 🐛 API endpoints returning 404 for valid merchants
- 🐛 False positive: FineJewelers 5% attributed to Pandora
- 🐛 Rakuten 4% found in logs but UI showed "Not available"
- ✨ Added descriptive logging for real-time backend progress

**Root Causes & Solutions:**

1. **Wrong URL Slugs:** Added `SLUG_OVERRIDES` and `SLUG_ALTERNATIVES` for merchants with non-obvious URLs:
   - `pandora` → `pandora-jewelry`
   - `ulta` → `ultabeauty`

2. **Search Page Strategy:** Implemented `_search_page()` as primary scraping method:
   - Rakuten: `/search?term=X&type=suggest`
   - TopCashback: `/search/merchants/?s=X`
   - More reliable than direct store page URLs

3. **False Positive Matching:** Removed loose fallback logic that grabbed ANY rate when merchant name appeared on page

4. **UI Transparency Fix:** ALL cashback offers now passed through to API:
   - Added `_found_cashback_offers` list to optimizer
   - Added `all_cashback_offers` field to `OptimizationResult`
   - Server uses actual scraper results instead of guessing

5. **Descriptive Logging:** Real-time progress updates:
   - `[SCRAPING]` logs when platforms are queued and searched
   - `[CASHBACK]` logs with ✓/✗ for found/not found
   - `[OPTIMIZER]` logs for product extraction and savings calculation
   - `[SUMMARY]` block at end with full breakdown

**Files Modified:**
| File | Changes |
|------|---------|
| `intelligence-core/cashback/scrapers/rakuten.py` | Added `_search_page()`, `SLUG_OVERRIDES`, fixed regex |
| `intelligence-core/cashback/scrapers/topcashback.py` | Added `_search_page()`, improved `_is_not_found()` |
| `intelligence-core/cashback/scrapers/honey.py` | Added `SLUG_OVERRIDES`, `_is_not_found()`, `_get_all_slugs()` |
| `intelligence-core/cashback/scrapers/befrugal.py` | Added `_search_page()`, `SLUG_OVERRIDES`, `_get_all_slugs()` |
| `intelligence-core/cashback/scrapers/swagbucks.py` | Added `SLUG_OVERRIDES`, `_is_not_found()`, improved matching |
| `intelligence-core/optimizer/net_price.py` | Store ALL offers, not just best; add `all_cashback_offers` |
| `intelligence-core/api/server.py` | Use actual offers for transparency instead of guessing |
| `app-frontend/main.py` | Enhanced UI progress with platform-by-platform status |

**Milestone:** Type URL in UI and watch browser load in dashboard

---

## 🏷️ v0.2.0 – Core Infrastructure (Docker Stack)
**Status:** ✅ Complete  
**Started:** 2026-01-03  
**Completed:** 2026-01-03

### Branch: `feature/docker-infrastructure`
**Created:** 2026-01-03  
**Merged:** Open  
**Purpose:** Initial project setup and Docker infrastructure

#### Commits:

| Commit | Date | Files Changed | Description |
|--------|------|---------------|-------------|
| `35f48e0` | 2026-01-03 | 18 files | Complete Docker infrastructure skeleton |
| `70f7524` | 2026-01-03 | 2 files | Documentation update with commit tracking |
| `2e68031` | 2026-01-03 | 5 files | Fix Docker infrastructure issues |

#### Session: 2026-01-03

**Test Runthrough Results:**
- ✅ Docker GPU access verified (nvidia-smi in container)
- ✅ All 6 services running and healthy
- ✅ NiceGUI frontend accessible at http://localhost:8080
- ✅ Ollama LLM loaded with Llama 3.1:8b model
- ✅ Playwright scraper with stealth patches operational
- ✅ Redis, MariaDB, Firefly III all healthy

**Files Created:**
- `docker-compose.yml` – Complete Docker Compose with 6 services and GPU passthrough
- `.env.example` – Environment configuration template with secure defaults
- `.gitignore` – Git ignore patterns for the project
- `app-frontend/Dockerfile` – NiceGUI container configuration
- `app-frontend/requirements.txt` – Python dependencies for frontend
- `app-frontend/main.py` – NiceGUI dashboard with command bar & visual debugger
- `scraper-engine/Dockerfile` – Playwright + Xvfb + GPU container
- `scraper-engine/requirements.txt` – Python dependencies for scraper
- `scraper-engine/run_scraper.py` – FastAPI scraper with real-time streaming
- `scraper-engine/start.sh` – Xvfb startup script for headful browser
- `intelligence-core/prompts/router.yaml` – LLM tool definitions
- `intelligence-core/tools/router.py` – Semantic router with function calling
- `scripts/start.sh` – Linux/Mac quick start script
- `scripts/start.ps1` – Windows PowerShell quick start script
- `configs/.gitkeep` – Placeholder for configuration files
- `.github/copilot-instructions.md` – Git workflow automation for Copilot

**Files Modified:**
- `README.md` – Updated with full project documentation and structure

#### Tasks Completed:

| Task | Status | Priority |
|------|--------|----------|
| Create `docker-compose.yml` with GPU passthrough | ✅ | 🔴 Critical |
| Verify `nvidia-smi` inside Docker container | ✅ | 🔴 Critical |
| Set up NiceGUI Hello World on port 8080 | ✅ | 🔴 Critical |
| Create `.env.example` template | ✅ | 🟡 Medium |
| Configure Docker network isolation | ✅ | 🟡 Medium |
| Create app-frontend Dockerfile | ✅ | 🔴 Critical |
| Create scraper-engine Dockerfile | ✅ | 🔴 Critical |
| Create intelligence-core router | ✅ | 🟡 Medium |
| Create startup scripts | ✅ | 🟢 Low |
| Pull Llama 3.1:8b model for Ollama | ✅ | 🔴 Critical |
| Fix playwright-stealth v2.0 API compatibility | ✅ | 🔴 Critical |

**Milestone:** Docker stack running with GPU access confirmed

---

## 🏷️ v0.1.0-alpha – Project Initialization
**Status:** ✅ Completed  
**Date:** 2026-01-03

### Branch: `main`
**Purpose:** Initial repository setup

#### Commits:

| Commit | Date | Files Changed | Description |
|--------|------|---------------|-------------|
| `initial` | 2026-01-03 | `LICENSE`, `README.md`, `research.txt` | Repository initialization |

#### Summary
- Established project foundation
- Added architectural specification (research.txt)
- Created initial README

**Milestone:** Repository initialized

---

## 📝 Changelog Format

When updating this changelog after commits, use the following format:

```markdown
### vX.Y.Z – Feature Name
**Date:** YYYY-MM-DD  
**Branch:** `branch-name`  
**Commit:** `commit-hash` or `commit-message-summary`

#### Changes
| File | Action | Description |
|------|--------|-------------|
| `file.py` | Created/Updated/Deleted | What changed |

#### Summary
Brief description of what was accomplished.
```

---

## 🏷️ Status Legend

| Icon | Meaning |
|------|---------|
| ⬜ | Not Started |
| 🔄 | In Progress |
| ✅ | Completed |
| ⏸️ | Paused |
| ❌ | Blocked |

| Priority | Meaning |
|----------|---------|
| 🔴 | Critical – Must have for phase completion |
| 🟡 | Medium – Important but not blocking |
| 🟢 | Low – Nice to have |

---

## 🔗 Related Documents

- [ROADMAP.md](ROADMAP.md) – Current work and future planning
- [README.md](README.md) – Project overview and setup
- [docs/API.md](docs/API.md) – API documentation
- [docs/FEATURES.md](docs/FEATURES.md) – User guide and architecture

---

<p align="center">
  <em>Last updated: 2026-01-04</em>
</p>
