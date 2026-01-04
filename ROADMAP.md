# SSIP Roadmap

> **Current Work & Future Planning**
> 
> For detailed version history and change logs, see [CHANGELOG.md](CHANGELOG.md)

---

## 📌 Current Version: `v0.8.0` – Cross-Retailer Comparison, QA & UX Polish

**Status:** ✅ Complete  
**Started:** 2026-01-03  
**Completed:** 2026-01-04  
**Last Updated:** 2026-01-04

---

## 📊 Detailed Version History

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

---

### Branch: `feature/price-tracking`
**Created:** 2026-01-04  
**Merged:** Open  
**Purpose:** Implement price tracking over time with history visualization

#### Commits:

| Commit | Date | Files Changed | Description |
|--------|------|---------------|-------------|
| `60808fc` | 2026-01-04 | 3 files | Price tracking over time feature |

#### Session: 2026-01-04 – Price Tracking Implementation

**Files Modified:**
- `app-frontend/database.py` – TrackedProduct/PricePoint dataclasses, 2 new tables, 8 tracking methods
- `app-frontend/main.py` – Price history UI in results, dedicated /tracking page, navbar links
- `app-frontend/tests/test_database.py` – 20+ tests for price tracking functionality

**Key Features Implemented:**
1. **Price History Schema:** TrackedProduct and PricePoint dataclasses for time-series data
2. **Database Tables:** `tracked_products` and `price_history` with proper indexes
3. **Automatic Tracking:** Products are tracked on each search with URL as unique key
4. **Price History Display:** Results page shows lowest/current/highest with drop percentage
5. **Dedicated Tracking Page:** `/tracking` route shows all tracked products with stats
6. **Alert Settings:** Target price and alert_enabled fields for future notifications
7. **Navigation:** "Tracking" link added to navbar (desktop and mobile menu)

**Database Schema (New):**
```sql
tracked_products (id, user_id, product_url, product_name, retailer, 
                  current_price, lowest_price, highest_price, target_price,
                  alert_enabled, first_tracked_at, last_checked_at)
price_history (id, product_id, price, net_price, best_cashback_rate, recorded_at)
```

**Price Tracking API Methods:**
- `track_product()` – Start/update tracking a product
- `get_tracked_product()` – Get single product with history
- `get_user_tracked_products()` – List all tracked products for user
- `get_product_price_history()` – Get price history for product
- `update_product_alert()` – Set target price and enable alerts
- `untrack_product()` – Stop tracking a product
- `get_products_with_price_drops()` – Get products below target price
- `get_price_tracking_stats()` – Aggregate stats for user

**UI Features:**
- Price history expansion in results page with lowest/current/highest stats
- Price drop percentage indicator ("↓ 15% below highest price")
- "Currently at lowest tracked price!" indicator with fire icon
- Recent prices list (last 5 observations with dates)
- Stats cards: Products Tracked, At Lowest Price, With Alerts

**Test Coverage Added:**
- `test_track_product_new` – Track a new product
- `test_track_product_price_update` – Price changes update history and bounds
- `test_get_tracked_product` / `test_get_tracked_product_not_found`
- `test_get_user_tracked_products` – List all tracked products
- `test_get_product_price_history` – Get price history
- `test_update_product_alert` – Set alert settings
- `test_untrack_product` – Stop tracking
- `test_get_products_with_price_drops` – Products below target
- `test_get_price_tracking_stats` – Aggregate statistics
- `TestTrackedProductDataclass` – `_calculate_drop_percent()`, `to_dict()`
- `TestPricePointDataclass` – `to_dict()` serialization

---

#### Tasks Progress:

| Task | Status | Priority |
|------|--------|----------|
| SQLite database for user accounts | ✅ | 🔴 Critical |
| Persist card wallet per user | ✅ | 🔴 Critical |
| Search history storage | ✅ | 🟡 Medium |
| Price tracking over time | ✅ | 🟡 Medium |
| Integrate RetailerIntelligence with frontend | ✅ | 🟡 Medium |
| User settings persistence (tax rate, location) | ✅ | 🟢 Low |

**Milestone:** User data persists across container restarts

---

| Commit | Date | Description |
|--------|------|-------------|
| `0364149` | 2026-01-06 | Fix `user_tax_rate` AttributeError - Updated User class and find_best_price() |
| `6aaba8c` | 2026-01-06 | Bug fixes and test suites for v0.8.0 QA |

---

## 🎯 Current Sprint: v0.8.0

### Overview

This release focuses on five major improvements identified during QA review:

1. **Cross-Retailer Price Comparison** – Find same product across multiple retailers to get true best price
2. **UI/UX Polish** – Fix visual inconsistencies and align with modern design standards
3. **User Settings Enhancements** – Account management, location detection, password reset
4. **Card Page Improvements** – Better card discovery, search, and professional card images
5. **Bug Fixes & Test Coverage** – Fix existing bugs and add comprehensive test cases

---

### 🎯 Feature 1: Cross-Retailer Price Comparison

**Problem:**  
Currently the app only finds cashback for the URL the user pastes. It doesn't search for the same product on other retailers where it might be cheaper even after cashback.

**Example Scenario:**
- User pastes: Pandora ring on pandora.net for $95
- Same ring on Macy's: $85 with 10% cashback = $76.50 net price
- **User should see both options and pick the true cheapest**

**Research Required:**
- [ ] Evaluate Google Shopping API (paid) vs open-source alternatives
- [ ] Research product matching algorithms (SKU, title similarity, image matching)
- [ ] Investigate free product search APIs (Google Shopping, PriceGrabber, etc.)
- [ ] Evaluate web scraping approach for major retailers

**Implementation Tasks:**

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Research product discovery APIs/tools | ⬜ | 🔴 Critical | Google Shopping, PriceGrabber, Shopzilla |
| Design cross-retailer search architecture | ⬜ | 🔴 Critical | How to match same product across sites |
| Build product identifier extraction | ⬜ | 🔴 Critical | Extract SKU, UPC, brand, model from URL |
| Implement multi-retailer search | ⬜ | 🔴 Critical | Query other retailers for same product |
| Build price comparison aggregator | ⬜ | 🟡 Medium | Combine product + cashback data |
| Create comparison results UI | ⬜ | 🟡 Medium | Show all retailer options sorted by net price |
| Cache product mappings in SQLite | ⬜ | 🟢 Low | Avoid re-searching known products |

**Potential Tools/APIs to Evaluate:**
- Google Shopping API (paid, but most comprehensive)
- SerpAPI (Google Shopping scraper, paid)
- Open source: Scrapy, BeautifulSoup for retailer scraping
- Product matching: Fuzzy string matching, image similarity APIs

---

### 🎯 Feature 2: UI/UX Design Polish

**Problems Identified:**
- Divs not properly aligned
- Navbar scroll reveals inconsistent backgrounds (green gradient → random rectangle → black)
- Overall design lacks cohesion

**Research Required:**
- [ ] Review modern SaaS dashboard design patterns
- [ ] Study NiceGUI layout best practices
- [ ] Evaluate Tailwind CSS patterns for consistent spacing

**Implementation Tasks:**

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Audit all pages for visual inconsistencies | ⬜ | 🔴 Critical | Document all issues |
| Fix navbar background consistency | ⬜ | 🔴 Critical | Solid/blur background on scroll |
| Align all div elements properly | ⬜ | 🔴 Critical | Consistent padding/margins |
| Create unified color scheme | ⬜ | 🟡 Medium | Define and apply design tokens |
| Fix page background layering | ⬜ | 🔴 Critical | Remove random rectangles |
| Implement consistent card styling | ⬜ | 🟡 Medium | Shadow, border-radius, padding |
| Add smooth scroll transitions | ⬜ | 🟢 Low | Polish animations |
| Mobile responsive review | ⬜ | 🟡 Medium | Test all breakpoints |

**Design Standards to Follow:**
- Consistent 8px spacing grid
- Max content width container
- Unified shadow/elevation system
- Consistent border-radius (8px cards, 4px inputs)

---

### 🎯 Feature 3: User Settings Enhancements

**Problems Identified:**
- No account deletion option
- No "forgot password" flow
- Location detection only gets state, not city (city tax rates differ)
- Need proper location consent flow

**Implementation Tasks:**

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Add "Delete Account" with confirmation | ⬜ | 🔴 Critical | GDPR-like data deletion |
| Implement "Forgot Password" email flow | ⬜ | 🔴 Critical | Password reset tokens |
| Enhance location detection (city + state) | ⬜ | 🔴 Critical | More accurate tax calculation |
| Add location consent popup | ⬜ | 🔴 Critical | Cookie/location permission UX |
| Allow manual address entry | ⬜ | 🟡 Medium | For users who deny location |
| Lookup city-level tax rates | ⬜ | 🟡 Medium | Integrate tax API with city granularity |
| Add email verification | ⬜ | 🟢 Low | Verify email on registration |
| Session management (view active sessions) | ⬜ | 🟢 Low | Security feature |

**Location Detection Approach:**
1. Show cookie/location consent popup on first visit
2. If allowed, use IP geolocation for city + state
3. If denied, prompt for manual address entry (zip code → city lookup)
4. Store and use for accurate tax calculation

**Tax Rate Sources:**
- Consider TaxJar API, Avalara, or open tax databases
- Need city-level granularity (e.g., NYC vs Buffalo have different rates)

---

### 🎯 Feature 4: Card Page Improvements

**Problems Identified:**
- Only 6 cards displayed
- No search functionality
- No professional card images
- Poor card discovery UX

**Implementation Tasks:**

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Research credit card image APIs/sources | ⬜ | 🔴 Critical | Legal, high-quality card images |
| Add card search functionality | ⬜ | 🔴 Critical | Filter by name, issuer, rewards type |
| Expand card database | ⬜ | 🔴 Critical | Add more popular cards |
| Create card image gallery | ⬜ | 🟡 Medium | Visual card recognition |
| Implement infinite scroll/pagination | ⬜ | 🟡 Medium | Handle large card list |
| Add card categories (travel, cashback, etc.) | ⬜ | 🟡 Medium | Filter by type |
| Show card benefits summary | ⬜ | 🟢 Low | Sign-up bonus, annual fee |
| Add "popular cards" section | ⬜ | 🟢 Low | Quick access to common cards |

**Card Image Sources to Research:**
- Card issuer media kits (official assets)
- Credit card review sites with image APIs
- Generate stylized card representations (avoid copyright issues)

---

### 🎯 Feature 5: Bug Fixes & QA Test Coverage

**Known Bugs:**

| Bug | Severity | File | Status |
|-----|----------|------|--------|
| `'AppState' object has no attribute 'user_tax_rate'` | 🔴 Critical | `main.py` | ✅ Fixed (`0364149`) |
| `authenticate_user` crashes on null email | 🔴 Critical | `database.py` | ✅ Fixed (`6aaba8c`) |
| `get_user_by_email` crashes on null email | 🟡 Medium | `database.py` | ✅ Fixed (`6aaba8c`) |
| `POPULAR_CARDS` iteration fails (factory vs object) | 🔴 Critical | `server.py` | ✅ Fixed (`6aaba8c`) |
| `CardInfo` allows empty name / negative rate | 🟡 Medium | `server.py` | ✅ Fixed (`6aaba8c`) |
| `/health` crashes if lifespan not run | 🟡 Medium | `server.py` | ✅ Fixed (`6aaba8c`) |

**QA Tasks:**

| Task | Status | Priority | Notes |
|------|--------|----------|-------|
| Fix `user_tax_rate` AttributeError | ✅ | 🔴 Critical | User class + find_best_price() fixed |
| Review all AppState attributes | ✅ | 🔴 Critical | No other broken refs found |
| Add input validation across all forms | ✅ | 🔴 Critical | `test_input_validation.py` (28 tests) |
| Add API error handling tests | ✅ | 🔴 Critical | `test_error_handling.py` (36 tests) |
| Create end-to-end test for product search | 🔜 | 🔴 Critical | *Future work* – requires browser automation |
| Test unauthenticated user flows | 🔜 | 🟡 Medium | *Future work* – ensure proper redirects |
| Test admin-only routes | 🔜 | 🟡 Medium | *Future work* – verify access control |
| Add database constraint tests | 🔜 | 🟡 Medium | *Future work* – foreign keys, unique constraints |
| Load testing with concurrent users | 🔜 | 🟢 Low | *Future work* – performance under load |
| Browser compatibility testing | 🔜 | 🟢 Low | *Future work* – Chrome, Firefox, Safari, Edge |

**Test Suites Added (2026-01-06):**

| File | Tests | Passed | Skipped | Coverage |
|------|-------|--------|---------|----------|
| `app-frontend/tests/test_input_validation.py` | 28 | 28 | 0 | Email, password, query, tax rate, location, auth |
| `intelligence-core/tests/test_error_handling.py` | 36 | 27 | 9 | Input validation, malformed requests, wallet, responses |

*Note: 9 tests skipped because they call endpoints that make real network requests (cashback providers)*

**Test Strategy:**
1. **Core Flow Tests** – Product search, cashback lookup, price optimization
2. **Auth Tests** – Login, register, logout, session handling
3. **Database Tests** – CRUD operations, constraints, persistence
4. **Error Handling** – Graceful degradation when services fail
5. **Edge Cases** – Empty states, invalid inputs, missing data

---

### 📊 v0.8.0 Tasks Progress Summary

| Feature | Critical | Medium | Low | Total |
|---------|----------|--------|-----|-------|
| Cross-Retailer Comparison | 4 | 2 | 1 | 7 |
| UI/UX Polish | 4 | 3 | 1 | 8 |
| User Settings | 4 | 2 | 2 | 8 |
| Card Page | 2 | 4 | 2 | 8 |
| Bug Fixes & QA | 5 | 3 | 2 | 10 |
| **Total** | **19** | **14** | **8** | **41** |

**Milestone:** Complete cross-retailer comparison, fix all known bugs, and polish UI/UX

---

## 🔮 Future Versions

### v0.9.0 – Notifications & Alerts
- [ ] Price drop email/push notifications
- [ ] Target price alerts implementation
- [ ] Cashback rate change alerts
- [ ] Weekly savings digest emails

### v1.0.0 – MVP Release
- [x] Core price optimization operational
- [x] Cashback comparison across 5 platforms
- [x] User authentication and data persistence
- [ ] Cross-retailer comparison complete
- [ ] All known bugs fixed
- [ ] Production-ready deployment
- [ ] Full documentation

### v1.1.0 – Mobile & PWA
- [ ] Progressive Web App support
- [ ] Mobile-optimized interface
- [ ] Push notifications

---

## 📜 Version History (Quick Reference)

| Version | Name | Status | Summary |
|---------|------|--------|---------|
| `v0.8.0` | Cross-Retailer Comparison, QA & UX Polish | 🔄 In Progress | Multi-retailer price comparison, UI fixes, settings enhancements |
| `v0.7.0` | Data Persistence & User Experience | ✅ Complete | SQLite user database, card wallet persistence, search history |
| `v0.6.0` | Frontend Integration, Testing & Docs | ✅ Complete | FastAPI server, NiceGUI redesign, 70+ test cases, API docs |
| `v0.5.0` | Sovereign Features | ✅ Complete | Vision parser, rewards schema, cashback monitor, net price optimizer |
| `v0.4.0` | Brain & Memory | ✅ Complete | Ollama LLM, Firefly III, semantic router, intent classification |
| `v0.3.0` | Eyes (Visual Browser) | ✅ Complete | Playwright scraper, stealth patches, real-time UI streaming |
| `v0.2.0` | Core Infrastructure | ✅ Complete | Docker stack with 6 services, GPU passthrough, all containers healthy |
| `v0.1.0-alpha` | Project Initialization | ✅ Complete | Repository setup, LICENSE, README, architecture spec |

> 📖 **See [CHANGELOG.md](CHANGELOG.md) for detailed commit history and session notes**

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

- [CHANGELOG.md](CHANGELOG.md) – Detailed version history and commit logs
- [README.md](README.md) – Project overview and setup
- [docs/API.md](docs/API.md) – API documentation
- [docs/FEATURES.md](docs/FEATURES.md) – User guide and architecture

---

<p align="center">
  <em>Last updated: 2026-01-04</em>
</p>
