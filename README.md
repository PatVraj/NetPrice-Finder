# Sovereign Smart Intelligence Platform (SSIP)

> **Zero-Cost, Data-Sovereign Financial Intelligence**

A local-first, event-driven microservices application that eliminates reliance on third-party financial aggregators by utilizing local GPU compute for AI inference and "headful" browser automation.

---

## 🎯 Overview

SSIP provides:
- **Financial Data Sovereignty** – All data stays on your hardware
- **Zero Marginal Cost** – No recurring SaaS subscriptions
- **High-Fidelity Automation** – GPU-accelerated browser automation with anti-bot evasion
- **Intelligent Routing** – Local LLM-powered intent classification and document parsing

---

## 🏗️ Project Structure

```
NetPrice-Finder/
├── .github/
│   └── copilot-instructions.md   # Copilot workflow automation
├── app-frontend/                  # NiceGUI Dashboard
│   ├── Dockerfile                 # Container configuration
│   ├── requirements.txt           # Python dependencies
│   └── main.py                    # Dashboard application
├── scraper-engine/                # Playwright + Xvfb + GPU
│   ├── Dockerfile                 # Container with GPU support
│   ├── requirements.txt           # Python dependencies
│   └── run_scraper.py             # Visual scraper with streaming
├── intelligence-core/             # Ollama LLM wrapper
│   ├── prompts/
│   │   └── router.yaml            # Tool definitions
│   └── tools/
│       └── router.py              # Semantic router
├── configs/                       # Service configurations
│   └── .gitkeep
├── scripts/
│   ├── start.sh                   # Linux/Mac quick start
│   └── start.ps1                  # Windows quick start
├── docker-compose.yml             # Container orchestration
├── .env.example                   # Environment template
├── .gitignore                     # Git ignore patterns
├── README.md                      # Project documentation
├── ROADMAP.md                     # Version tracking & changelog
├── LICENSE                        # License file
└── research.txt                   # Architectural specification
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Orchestration** | Docker Compose v2.4+ | GPU-enabled container management |
| **Frontend** | NiceGUI (Python) | WebSocket-driven reactive UI |
| **Scraper** | Playwright + Xvfb | Headful browser automation |
| **AI/LLM** | Ollama (Llama 3 / Mistral) | Intent routing & document parsing |
| **Ledger** | Firefly III + MariaDB | Financial data storage |
| **Message Bus** | Redis | Async jobs & video streaming |
| **GPU Runtime** | NVIDIA Container Toolkit | WebGL masquerading & AI inference |

---

## ⚡ Quick Start

> **Prerequisites:** Docker, Docker Compose, NVIDIA GPU with drivers, NVIDIA Container Toolkit

### Linux / macOS
```bash
# Clone the repository
git clone https://github.com/your-username/NetPrice-Finder.git
cd NetPrice-Finder

# Run the quick start script
chmod +x scripts/start.sh
./scripts/start.sh
```

### Windows (PowerShell)
```powershell
# Clone the repository
git clone https://github.com/your-username/NetPrice-Finder.git
cd NetPrice-Finder

# Run the quick start script
.\scripts\start.ps1
```

### Manual Setup
```bash
# Copy environment template and edit as needed
cp .env.example .env

# Build and start all services
docker compose up -d

# Pull an LLM model
docker compose exec intelligence-core ollama pull llama3.1:8b

# Access the dashboard
open http://localhost:8080
```

---

## 🖥️ Service Endpoints

| Service | URL | Description |
|---------|-----|-------------|
| **Dashboard** | http://localhost:8080 | NiceGUI frontend |
| **Firefly III** | http://localhost:8081 | Financial ledger |
| **Ollama API** | http://localhost:11434 | LLM inference |

---

## 🔧 Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| GPU | NVIDIA GTX 1080 (8GB VRAM) | NVIDIA RTX 3090/4090 (24GB VRAM) |
| RAM | 16GB | 32GB+ |
| Storage | 50GB SSD | 256GB NVMe |
| CPU | 4 cores | 8+ cores |

---

## 📚 Documentation

- [ROADMAP.md](ROADMAP.md) – Version history & planned features
- [research.txt](research.txt) – Full architectural specification
- [.github/copilot-instructions.md](.github/copilot-instructions.md) – Development workflow

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Update ROADMAP.md with your changes
5. Commit (`git commit -m '[phase-X] Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

---

## 📄 License

See [LICENSE](LICENSE) for details.

---

<p align="center">
  <strong>Built for Privacy. Designed for Performance.</strong><br>
  <em>Version 0.2.0</em>
</p>
