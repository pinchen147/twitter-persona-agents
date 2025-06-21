# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Activate virtual environment (already exists)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt          # Production dependencies
pip install -r requirements-dev.txt     # Development dependencies
```

### Local Development
```bash
# Start locally with auto-reload
./start_local.sh
# OR manually:
uvicorn app.main:app --host 0.0.0.0 --port 8582 --reload

# Start with Docker
./start_docker.sh
# OR manually:
docker-compose -f docker/docker-compose.yml up --build
```

### Testing
```bash
# Run all tests
pytest

# Run specific test types
pytest -m unit           # Unit tests only
pytest -m integration    # Integration tests only
pytest -m slow          # Slow tests with external APIs

# Run with coverage
pytest --cov=app --cov-report=html

# Run single test file
pytest tests/unit/test_monitoring.py
```

### Code Quality
```bash
# Format code
black .
isort .

# Type checking
mypy app/

# Linting
flake8

# Run all quality checks
black . && isort . && mypy app/ && flake8
```

### Knowledge Base Management
```bash
# Build/rebuild knowledge base from PDFs
python -m ingest.split_embed

# Ingest specific content
python -m ingest.ingest_paulgraham     # Paul Graham essays
python -m ingest.ingest_pdf            # General PDF processing
```

### Multi-Account Migration
```bash
# Migrate from single to multi-account setup
python scripts/migrate_to_multi_account.py
```

## System Architecture

### Multi-Account Design
This is a **multi-account Twitter bot system** where each account operates independently:
- **Account Configuration**: Each account defined in `accounts/{account_id}.json`
- **Independent Personas**: Unique voice, exemplar tweets, and knowledge bases per account
- **Unified Scheduling**: Single scheduler posts to all accounts (every 6 hours = 4 posts/day)
- **Shared Infrastructure**: Common generation engine, monitoring, and health systems

### Core Components

#### 1. Application Layer (`app/`)
- **`main.py`**: FastAPI web server with dashboard UI and REST API
- **`account_manager.py`**: Multi-account configuration management
- **`generation.py`**: Tweet generation engine with RAG (Retrieval-Augmented Generation)
- **`twitter_client.py`**: Twitter API v2 integration with rate limiting
- **`scheduler.py`**: APScheduler-based posting automation with catch-up logic
- **`monitoring.py`**: Cost tracking, activity logging, and health checks
- **`security.py`**: Content filtering and moderation
- **`vector_search.py`**: ChromaDB integration for semantic search

#### 2. Data Pipeline (`ingest/`)
- **PDF Processing**: Extract and clean text from philosophical books
- **Chunking Strategy**: Large chunks (~1500 words) to preserve context
- **Vector Embeddings**: OpenAI text-embedding-3-small for semantic search
- **ChromaDB Storage**: Local vector database with account-specific collections

#### 3. Generation Pipeline
1. **Random Seed Selection**: Choose random chunk from account's knowledge base
2. **Context Retrieval**: k-NN semantic search for related content
3. **Dynamic Prompting**: Jinja2 templates combining persona + context + exemplars
4. **Content Safety**: Multi-layer filtering (rules + OpenAI moderation)
5. **Tweet Refinement**: Auto-shortening if >280 characters

### Configuration Structure

#### Account Configuration (`accounts/{account_id}.json`)
```json
{
  "account_id": "unique_identifier",
  "display_name": "Human Readable Name",
  "persona": "Personality and voice description...",
  "exemplars": ["Example tweet 1", "Example tweet 2"],
  "vector_collection": "knowledge_collection_name",
  "twitter_credentials": {
    "bearer_token": "env:TWITTER_BEARER_TOKEN",
    "api_key": "env:TWITTER_API_KEY"
  }
}
```

#### Main Configuration (`config/config.yaml`)
- **Scheduler**: Posting intervals, catch-up logic, timezone settings
- **OpenAI**: Model selection (gpt-4.1 for creativity, o3 for reasoning)
- **Content Safety**: Moderation settings, profanity filters
- **Cost Management**: Daily limits, emergency stops

#### Environment Variables (`.env`)
Required API credentials for all services (OpenAI, Twitter).

## Key Features

### Catch-Up Posting System
- **Missed Run Detection**: On startup, checks for missed posting opportunities
- **Automatic Scheduling**: Schedules catch-up posts with configurable limits
- **Grace Period**: 1-hour buffer before posts are considered "missed"
- **Rate Limiting**: 30-second intervals between catch-up posts

### Content Safety
- **OpenAI Moderation**: Automatic content screening
- **Political Filtering**: Avoids controversial topics
- **Profanity Protection**: Configurable word filtering
- **Emergency Controls**: Immediate stop capabilities

### Monitoring & Observability
- **Cost Tracking**: Real-time API cost monitoring with daily limits
- **Activity Logging**: Complete posting history per account
- **Health Checks**: `/health` (basic) and `/health/deep` (comprehensive)
- **Structured Logging**: JSON logs with correlation IDs

## API Endpoints

### Multi-Account Operations
- `GET /api/accounts` - List all configured accounts
- `GET /api/status/{account_id}` - Account-specific status
- `POST /api/force-post/{account_id}` - Manual posting
- `POST /api/test-generation/{account_id}` - Test tweet generation
- `GET /api/search-chunks/{account_id}?query=...` - Search knowledge base

### System Operations
- `GET /health` - Basic health check
- `GET /health/deep` - Comprehensive system validation
- `POST /emergency-stop` - Emergency stop all posting
- `GET /api/cost-summary` - Cost tracking summary

## Development Workflow

### Adding New Accounts
1. Create `accounts/new_account.json` with account configuration
2. Add Twitter credentials to `.env`
3. Restart application (auto-discovery of new accounts)
4. Optionally create account-specific knowledge base collections

### Testing Changes
1. Use test mode (`twitter.post_enabled: false` in config)
2. Generate test tweets via `/api/test-generation/{account_id}`
3. Monitor logs and health endpoints
4. Run full test suite before deployment

### Deployment
- **Local**: Use `start_local.sh` for development
- **Docker**: Use `start_docker.sh` for containerized deployment  
- **Production**: Configure environment variables and run with gunicorn/uvicorn

## 24/7 Deployment Options

### Quick Start (Recommended)
```bash
# One-command 24/7 deployment
./deploy-24-7.sh
```

### Manual Docker Deployment
```bash
# Production deployment with auto-restart
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Stop services
docker-compose -f docker-compose.prod.yml down
```

### Systemd Service (Linux Servers)
```bash
# Install as system service (requires sudo)
sudo ./scripts/install-systemd-service.sh

# Service management
sudo systemctl start twitter-persona-agents
sudo systemctl stop twitter-persona-agents
sudo systemctl status twitter-persona-agents
sudo journalctl -u twitter-persona-agents -f
```

### Cloud Deployment Options

#### DigitalOcean Droplet ($6/month)
```bash
# Create droplet with Docker pre-installed
# Clone repo and run deployment script
git clone <your-repo>
cd twitter-persona-agents
./deploy-24-7.sh
```

#### AWS EC2 (t3.micro free tier)
```bash
# Launch t3.micro instance with Amazon Linux
# Install Docker and Docker Compose
sudo yum update -y
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -a -G docker ec2-user

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Deploy your bot
git clone <your-repo>
cd twitter-persona-agents
./deploy-24-7.sh
```

#### Google Cloud Run (Serverless)
```bash
# Build and push to Container Registry
docker build -f docker/Dockerfile -t gcr.io/PROJECT-ID/twitter-persona-agents .
docker push gcr.io/PROJECT-ID/twitter-persona-agents

# Deploy to Cloud Run with persistent storage
gcloud run deploy twitter-persona-agents \
  --image gcr.io/PROJECT-ID/twitter-persona-agents \
  --platform managed \
  --region us-central1 \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 1 \
  --max-instances 1 \
  --set-env-vars ENVIRONMENT=production
```

### Production Features
- **Auto-restart**: `restart: unless-stopped` policy
- **Health checks**: Container-level health monitoring
- **Resource limits**: Memory and CPU constraints
- **Log rotation**: Prevents disk space issues
- **Redis persistence**: Data survives container restarts
- **Watchtower**: Optional auto-updates

## Data Storage
- **Vector Database**: `data/chroma/` (ChromaDB persistence)
- **Activity Logs**: `data/post_history.db` (SQLite)
- **Cost Tracking**: `data/cost_tracking.db` (SQLite) 
- **Source Material**: `data/source_material/` (PDF books)