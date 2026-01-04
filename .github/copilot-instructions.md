# GitHub Copilot Instructions for SSIP

## 🔄 Automatic Roadmap Update Workflow

**CRITICAL:** After completing ANY code changes in this repository, the agent MUST follow this workflow:

---

## 🚨 MANDATORY GIT WORKFLOW (Before Updating ROADMAP.md)

**NEVER commit directly to `main` branch. ALWAYS use feature branches.**

### Step 1: Verify Current Branch
Before making ANY commits, run:
```bash
git branch --show-current
```

### Step 2: Create Feature Branch (if on main)
If currently on `main`, create and switch to a feature branch:
```bash
git checkout -b feature/<descriptive-name>
```

Branch naming conventions:
- `feature/<name>` – New features
- `fix/<name>` – Bug fixes
- `docs/<name>` – Documentation updates
- `refactor/<name>` – Code refactoring

### Step 3: Stage and Commit Changes
```bash
# Check what files changed
git status

# Stage all changes
git add -A

# Commit with proper message format
git commit -m "[phase-X] Brief description" -m "- Detailed change 1" -m "- Detailed change 2"
```

### Step 4: Get Commit Hash for ROADMAP.md
```bash
git log -1 --format="%h"
```

### Step 5: NOW Update ROADMAP.md, CHANGELOG.md, and README.md
Only after the commit is made, update the documentation with the actual commit hash.

### Step 6: Commit Documentation Updates
```bash
git add ROADMAP.md CHANGELOG.md README.md
git commit -m "[docs] Update roadmap and changelog with changes"
```

---

## 📋 Complete Agent Workflow

```
1. Make code changes
2. Run: git branch --show-current
3. If on main → git checkout -b feature/<name>
4. Run: git add -A && git status (verify files)
5. Run: git commit -m "[phase-X] Description"
6. Run: git log -1 --format="%h" (get commit hash)
7. Update ROADMAP.md with commit hash and changes
8. Update CHANGELOG.md with session details (files, changes, features)
9. Update README.md if structure changed
10. Run: git add ROADMAP.md CHANGELOG.md README.md
11. Run: git commit -m "[docs] Update roadmap and changelog"
```

---

## ⛔ PROTECTED: main Branch Rules

The agent MUST:
1. **NEVER** run `git checkout main` followed by commits
2. **ALWAYS** verify branch before committing: `git branch --show-current`
3. **REFUSE** to commit if on `main` – create a feature branch first
4. **INCLUDE** the branch name in ROADMAP.md entries

If accidentally on main:
```bash
# Stash changes, create branch, apply changes
git stash
git checkout -b feature/<name>
git stash pop
```

---

### Post-Change Checklist

1. **Update ROADMAP.md** with:
   - Current version section
   - Branch name where changes occurred
   - Commit-level details of what changed (use actual commit hash)
   - Update task status (⬜ → ✅)

2. **Update CHANGELOG.md** when:
   - Any task is marked complete (⬜ → ✅) in ROADMAP.md
   - Any bug is fixed
   - Any feature is implemented
   - A version/milestone is completed
   
   CHANGELOG.md format:
   ```markdown
   #### Session: YYYY-MM-DD – Description
   
   **Files Created:**
   - `path/to/file.py` – Description of purpose
   
   **Files Modified:**
   - `path/to/file.py` – What changed
   
   **Key Changes:**
   1. Brief description of change 1
   2. Brief description of change 2
   ```

3. **Review README.md** for:
   - Any structural changes that need documentation
   - New dependencies or setup steps
   - Updated project structure if files were added/removed

4. **Commit Message Format:**
   ```
   [phase-X] Brief description
   
   - Detailed change 1
   - Detailed change 2
   ```

---

## 📋 ROADMAP.md Update Format

When updating the roadmap, use this hierarchical structure:

### Version Level (Major Milestones)
```markdown
## 🏷️ v0.2.0 – Core Infrastructure
**Status:** 🔄 In Progress  
**Started:** YYYY-MM-DD  
**Target Completion:** YYYY-MM-DD
```

### Branch Level (Feature Work)
```markdown
### Branch: `feature/docker-setup`
**Created:** YYYY-MM-DD  
**Merged:** YYYY-MM-DD (or "Open")  
**Purpose:** Set up Docker Compose with GPU passthrough

#### Commits:
```

### Commit Level (Atomic Changes)
```markdown
| Commit | Date | Files Changed | Description |
|--------|------|---------------|-------------|
| `abc1234` | YYYY-MM-DD | `docker-compose.yml`, `.env.example` | Initial Docker config |
| `def5678` | YYYY-MM-DD | `app-frontend/Dockerfile` | NiceGUI container setup |
```

---

## 🎯 Task Status Updates

When completing tasks in ROADMAP.md:

```markdown
# Before
| Create `docker-compose.yml` with GPU passthrough | ⬜ | 🔴 Critical |

# After  
| Create `docker-compose.yml` with GPU passthrough | ✅ | 🔴 Critical |
```

---

## 📝 CHANGELOG.md Update Format

When any task is completed or bug is fixed, add a session entry to CHANGELOG.md under the current version:

### Session Entry Format
```markdown
#### Session: YYYY-MM-DD – Brief Description of Work

**Files Created:**
- `path/to/new/file.py` – Purpose of the file

**Files Modified:**
- `path/to/modified/file.py` – What was changed

**Key Changes:**
1. Concise description of major change 1
2. Concise description of major change 2

**Bugs Fixed:**
- Bug description → Fix applied
```

### When to Update CHANGELOG.md
- ✅ After fixing any bug
- ✅ After implementing any feature
- ✅ After adding test suites
- ✅ After any code review fixes
- ✅ When marking tasks complete in ROADMAP.md
- ❌ Do NOT update for documentation-only changes (ROADMAP/README updates)

---

## 📁 File Change Tracking

For each editing session, track:

```markdown
#### Session: YYYY-MM-DD HH:MM

**Files Created:**
- `path/to/new/file.py` - Description

**Files Modified:**
- `path/to/existing/file.py` - What changed

**Files Deleted:**
- `path/to/removed/file.py` - Why removed
```

---

## 🔧 Development Standards

### Docker Services
- All services must be defined in `docker-compose.yml`
- GPU services require `runtime: nvidia` or deploy.resources.reservations
- Use environment variables from `.env` file
- Internal services should NOT expose ports to host

### Python Code
- Use type hints for all functions
- Follow PEP 8 style guidelines
- Use async/await for I/O operations
- Pydantic models for data validation

### NiceGUI Components
- Prefer `ui.row()` and `ui.column()` for layouts
- Use `ui.notify()` for user feedback
- WebSocket updates via `ui.timer()` or async handlers

### Playwright Scraping
- Always use `headless=False` with Xvfb
- Apply stealth patches before navigation
- Capture screenshots at 10-15 FPS for streaming
- Handle timeouts gracefully

---

## 📝 README Review Checklist

After changes, verify README.md includes:

- [ ] Updated project structure if files added
- [ ] New dependencies listed
- [ ] Any new environment variables documented
- [ ] Quick start steps still accurate
- [ ] Links to new documentation files

---

## 🚨 Mandatory Final Steps

**EVERY agent session MUST end with:**

1. ✅ ROADMAP.md updated with all changes
2. ✅ README.md reviewed and updated if needed
3. ✅ All new files listed in project structure
4. ✅ Version/branch/commit hierarchy maintained
5. ✅ Task statuses reflect current state

---

## 🏗️ Project Architecture Reference

```
┌─────────────────────────────────────────────────────────────┐
│                     User Browser (:8080)                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    app-frontend (NiceGUI)                    │
│              WebSocket Server + REST Gateway                 │
└─────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  scraper-engine │  │intelligence-core│  │   firefly-iii   │
│   (Playwright)  │  │    (Ollama)     │  │   (Ledger DB)   │
│   GPU: WebGL    │  │   GPU: CUDA     │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
           │                    │                    │
           └────────────────────┼────────────────────┘
                                ▼
                    ┌─────────────────┐
                    │      Redis      │
                    │  (Message Bus)  │
                    └─────────────────┘
```
