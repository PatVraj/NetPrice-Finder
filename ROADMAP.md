# SSIP Roadmap

> **Current Work & Future Planning**
> 
> For detailed version history and change logs, see [CHANGELOG.md](CHANGELOG.md)

---

## 📌 Current Version: `v0.8.0` – Cross-Retailer Comparison, QA & UX Polish

**Status:** 🔄 In Progress  
**Started:** 2026-01-04  
**Target Completion:** 2026-01-20  
**Last Updated:** 2026-01-06

### 🔄 Active Branch: `feature/v0.8-bugfixes`

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
