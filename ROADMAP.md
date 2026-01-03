# SSIP Roadmap & Changelog

> **Version Tracking, Change History, and Future Planning**
> 
> **Structure:** Version (high-level) → Branch (feature work) → Commit (atomic changes)

---

## 📌 Current Version: `v0.2.0` – Core Infrastructure

**Status:** 🔄 In Progress  
**Started:** 2026-01-03  
**Target Completion:** 2026-01-06  
**Last Updated:** 2026-01-03

---

## 📊 Detailed Version History

---

## 🏷️ v0.2.0 – Core Infrastructure
**Status:** 🔄 In Progress  
**Started:** 2026-01-03  
**Target Completion:** 2026-01-06

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

#### Session: 2026-01-03 (Latest)

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

---

### Tasks for v0.2.0

| Task | Status | Priority | Branch |
|------|--------|----------|--------|
| Create `docker-compose.yml` with GPU passthrough | ✅ | 🔴 Critical | `feature/docker-infrastructure` |
| Verify `nvidia-smi` inside Docker container | ✅ | 🔴 Critical | `feature/docker-infrastructure` |
| Set up NiceGUI Hello World on port 8080 | ✅ | 🔴 Critical | `feature/docker-infrastructure` |
| Create `.env.example` template | ✅ | 🟡 Medium | `feature/docker-infrastructure` |
| Configure Docker network isolation | ✅ | 🟡 Medium | `feature/docker-infrastructure` |
| Create app-frontend Dockerfile | ✅ | 🔴 Critical | `feature/docker-infrastructure` |
| Create scraper-engine Dockerfile | ✅ | 🔴 Critical | `feature/docker-infrastructure` |
| Create intelligence-core router | ✅ | 🟡 Medium | `feature/docker-infrastructure` |
| Create startup scripts | ✅ | 🟢 Low | `feature/docker-infrastructure` |
| Pull Llama 3.1:8b model for Ollama | ✅ | 🔴 Critical | `feature/docker-infrastructure` |
| Fix playwright-stealth v2.0 API compatibility | ✅ | 🔴 Critical | `feature/docker-infrastructure` |

**Milestone:** ✅ Docker stack running with GPU access confirmed

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

---

## 🗺️ Development Phases

### Phase 1: The "Skeleton" 🦴
**Target:** v0.2.0 | **Status:** ✅ Complete

| Task | Status | Priority |
|------|--------|----------|
| Create `docker-compose.yml` with GPU passthrough | ✅ | 🔴 Critical |
| Verify `nvidia-smi` inside Docker container | ⬜ | 🔴 Critical |
| Set up NiceGUI Hello World on port 8080 | ✅ | 🔴 Critical |
| Create `.env.example` template | ✅ | 🟡 Medium |
| Configure Docker network isolation | ✅ | 🟡 Medium |

**Milestone:** Docker stack running with GPU access confirmed

---

### Phase 2: The "Eyes" 👁️
**Target:** v0.3.0 | **Status:** ✅ Complete

| Task | Status | Priority |
|------|--------|----------|
| Create `scraper-engine/Dockerfile` with Xvfb | ✅ | 🔴 Critical |
| Implement Playwright with stealth patches | ✅ | 🔴 Critical |
| Build screencast pipeline (Screenshot → Base64 → Redis) | ✅ | 🔴 Critical |
| Integrate `ui.interactive_image` in NiceGUI | ✅ | 🔴 Critical |
| Implement click-relay from UI to Playwright | ✅ | 🟡 Medium |
| Test end-to-end visual debugging | ✅ | 🔴 Critical |

**Milestone:** ✅ Type URL in UI and watch browser load in dashboard

---

### Phase 3: The "Brain" & "Memory" 🧠
**Target:** v0.4.0 | **Status:** ✅ Complete

| Task | Status | Priority |
|------|--------|----------|
| Deploy Ollama container with Llama 3 | ✅ | 🔴 Critical |
| Create semantic router function calling | ✅ | 🔴 Critical |
| Deploy Firefly III + MariaDB | ✅ | 🔴 Critical |
| Expose Firefly III on port 8081 | ✅ | 🟡 Medium |
| Generate Firefly API token | ✅ | 🟡 Medium |
| Build Python wrapper for Firefly API | ✅ | 🟡 Medium |
| Implement intent classification prompts | ✅ | 🟡 Medium |

**Milestone:** ✅ User query routes correctly to scraper or ledger

---

### Phase 4: "Sovereign" Features 👑
**Target:** v0.5.0 | **Status:** ✅ Complete

| Task | Status | Priority |
|------|--------|----------|
| Implement Vision Parser for PDF statements | ✅ | 🔴 Critical |
| Build MCC enrichment pipeline | ✅ | 🟡 Medium |
| Create Credit Card Reward Schema system | ✅ | 🟡 Medium |
| Build Net Price Optimizer | ✅ | 🔴 Critical |
| Implement Cashback Monitor scraper | ✅ | 🟡 Medium |
| Clarify credit card rewards are OPTIONAL | ✅ | 🟡 Medium |

**Milestone:** ✅ Full sovereign financial intelligence operational

---

### Phase 5: Frontend Integration 🖥️
**Target:** v0.6.0 | **Status:** ✅ Complete

| Task | Status | Priority |
|------|--------|----------|
| Create FastAPI server for optimizer | ✅ | 🔴 Critical |
| Build price optimization endpoints | ✅ | 🔴 Critical |
| Create card wallet management API | ✅ | 🟡 Medium |
| Redesign NiceGUI frontend | ✅ | 🔴 Critical |
| Implement search hero component | ✅ | 🟡 Medium |
| Build results display page | ✅ | 🔴 Critical |
| Create card wallet management UI | ✅ | 🟡 Medium |
| Add quick calculator widget | ✅ | 🟢 Low |

**Milestone:** ✅ User can paste a link and see net price breakdown

---

### Phase 6: Testing & Documentation 📚
**Target:** v0.6.0 | **Status:** ✅ Complete

| Task | Status | Priority |
|------|--------|----------|
| Create pytest test suite for optimizer | ✅ | 🔴 Critical |
| Create tests for credit card rewards | ✅ | 🔴 Critical |
| Create tests for API endpoints | ✅ | 🔴 Critical |
| Write comprehensive API documentation | ✅ | 🟡 Medium |
| Write features/user guide documentation | ✅ | 🟡 Medium |
| Verify tests run in Docker containers | ✅ | 🟡 Medium |

**Milestone:** ✅ 70+ test cases and full API/features documentation

---

### Branch: `feature/phase4-sovereign-features`
**Created:** 2026-01-04  
**Merged:** Open  
**Purpose:** Net Price Finder - find TRUE cheapest price after all savings stack

#### Commits:

| Commit | Date | Files Changed | Description |
|--------|------|---------------|-------------|
| `bbf7279` | 2026-01-04 | 3 files | Vision Parser for PDFs + MCC enrichment |
| `8e5c8d6` | 2026-01-04 | 4 files | Credit Card Reward Schema + Cashback Monitor |
| `43c97c2` | 2026-01-04 | 4 files | Net Price Optimizer - core intelligence |
| `19d8ff0` | 2026-01-04 | 1 file | Clarify credit card rewards are optional |
| `642c106` | 2026-01-04 | 1 file | Update roadmap with Phase 4 details |
| `866c0d2` | 2026-01-03 | 3 files | Frontend integration with Net Price Optimizer |
| `4ade820` | 2026-01-03 | 6 files | Comprehensive test suite and API documentation |

#### Files Created (Phase 4):
- `intelligence-core/vision/parser.py` – PDF/receipt parsing with LLaVA
- `intelligence-core/vision/__init__.py` – Module exports
- `intelligence-core/rewards/schema.py` – Credit card reward optimization
- `intelligence-core/rewards/__init__.py` – Module exports
- `intelligence-core/cashback/monitor.py` – Multi-platform cashback scraping
- `intelligence-core/cashback/__init__.py` – Module exports
- `intelligence-core/optimizer/net_price.py` – Net Price Optimizer (core)
- `intelligence-core/optimizer/__init__.py` – Module exports

#### Files Created (Phase 5 - Frontend Integration):
- `intelligence-core/api/server.py` – FastAPI server for optimizer endpoints
- `intelligence-core/api/__init__.py` – Module exports

#### Files Modified (Phase 5):
- `app-frontend/main.py` – Complete rewrite with Net Price Finder UI
- `intelligence-core/optimizer/__init__.py` – Module exports

#### Files Created (Phase 6 - Testing & Documentation):
- `intelligence-core/tests/__init__.py` – Test suite initialization
- `intelligence-core/tests/test_net_price.py` – 25+ test cases for optimizer
- `intelligence-core/tests/test_rewards.py` – 20+ test cases for card rewards
- `intelligence-core/tests/test_api.py` – 25+ test cases for API endpoints
- `docs/API.md` – Comprehensive API endpoint documentation
- `docs/FEATURES.md` – User guide and architecture documentation

#### Key Design Decisions:
1. **Credit card rewards are OPTIONAL** – Only user's actual cards are used
2. **Cashback stacking** – Compares 5 platforms: Rakuten, Honey, TopCashback, BeFrugal, Swagbucks
3. **Coupon finding** – Scrapes coupons from RetailMeNot, Honey, vendor sites
4. **Net price calculation** – Product - Coupon + Tax - Cashback - Card Rewards = TRUE cost

---

## 🔮 Future Versions

### v0.2.0 – Core Infrastructure
- [ ] Complete Docker Compose with all services
- [ ] GPU passthrough for WebGL + CUDA
- [ ] Basic NiceGUI dashboard layout

### v0.3.0 – Visual Scraping
- [ ] Playwright screencast streaming
- [ ] Interactive image with click relay
- [ ] Anti-bot evasion (stealth patches)

### v0.4.0 – Intelligence Integration
- [ ] Ollama semantic routing
- [ ] Function calling implementation
- [ ] Firefly III API integration

### v0.5.0 – Document Parsing
- [ ] PDF to image conversion
- [ ] Vision LLM parsing (Llava)
- [ ] Pydantic validation pipeline

### v1.0.0 – MVP Release
- [ ] All core features operational
- [ ] Documentation complete
- [ ] Production-ready deployment

---

## 📝 Changelog Format

When updating this roadmap after commits, use the following format:

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

- [README.md](README.md) – Project overview and setup
- [research.txt](research.txt) – Full architectural specification

---

<p align="center">
  <em>Last updated: 2026-01-03 (Testing & Documentation Phase Complete)</em>
</p>
