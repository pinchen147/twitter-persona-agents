# Multi-Platform Persona Agents 🧘✨

![Project Status: Production Ready](https://img.shields.io/badge/status-production_ready-brightgreen)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python: 3.11+](https://img.shields.io/badge/python-3.11+-blue)
![Multi-Account Support](https://img.shields.io/badge/multi--account-supported-orange)

A **multi-account autonomous social media agent** that generates and posts insightful content across **Twitter and Meta's Threads** by synthesizing philosophical teachings. Originally designed to blend **Eckhart Tolle** (presence, mindfulness, ego-dissolution) and **Carolyn Elliott** (existential kink, shadow work), the system now supports unlimited accounts across multiple platforms with unique personas.

The system is built on a core philosophy of **simplicity and ruthless pragmatism**. Each account can have its own personality, knowledge base, and posting style across multiple social media platforms, managed through a unified control panel.

## ⚡ Ready to Run

**The environment is already set up!** Just follow these steps:

1. **Activate virtual environment**: `source venv/bin/activate`
2. **Add API keys**: Copy `config/secrets.env.example` to `config/.env` and add your keys
3. **Run migration**: `python scripts/migrate_to_multi_account.py` 
4. **Add PDF books**: Place them in `data/source_material/`
5. **Build knowledge base**: `python -m ingest.split_embed`
6. **Start application**: `uvicorn app.main:app --host 0.0.0.0 --port 8582 --reload`
7. **Open control panel**: http://localhost:8582
8. **build in dockerdocker**: `docker-compose -f docker-compose.prod.yml up -d`
      .

## 🔄 Multi-Account Features

### **Multi-Platform Account Management**
- **Multiple accounts** posting simultaneously across **Twitter and Threads**
- **Account-specific personas** and exemplar posts for each platform
- **Shared or separate knowledge bases** per account
- **Unified scheduler** posts content to all enabled platforms every 6 hours (4 posts/day)
- **Platform-specific adaptation** (Twitter 280 chars, Threads 500 chars)
- **Missed runs handling** with automatic catch-up posts
- **Easy account addition** via JSON configuration files

### **📅 Smart Multi-Platform Scheduling & Catch-Up System**
- **Simultaneous posting**: Each post goes to all enabled platforms (Twitter + Threads) simultaneously
- **Automatic catch-up**: When your system restarts after being offline, it detects missed posting opportunities and schedules catch-up posts
- **Configurable intervals**: Default 6-hour posting schedule (4 posts/day) balances consistency with avoiding spam
- **Grace period**: 1-hour buffer before posts are considered "missed" to avoid unnecessary catch-ups
- **Intelligent limits**: Maximum 3 catch-up posts per account to prevent flooding timelines
- **Staggered posting**: Catch-up posts are spaced 30 seconds apart to respect rate limits

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker (optional but recommended)
- OpenAI API key
- Twitter API v2 credentials (Bearer token, API keys, Access tokens)
- Meta Threads API credentials (Access token, User ID)

### 1. Clone and Setup
```bash
git clone <your-repo-url>
cd multi-platform-persona-agents

# The virtual environment 'venv' is already created for you!
# Just activate it:
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Dependencies are already installed, but you can update them if needed:
# pip install -r requirements.txt
```

### 2. Configuration
```bash
# Copy configuration templates
cp config/config.example.yaml config/config.yaml
cp config/secrets.env.example config/.env

# Edit your API keys in config/.env
nano config/.env

# Run the multi-account migration
python scripts/migrate_to_multi_account.py
```

### 3. Add Source Material
```bash
# Place PDF books in the source directory
mkdir -p data/source_material
# Copy your Eckhart Tolle and Carolyn Elliott PDFs here
```

### 4. Build Knowledge Base
```bash
# Process PDFs and create vector embeddings
python -m ingest.split_embed
```

### 5. Run the Application
```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Start the web application
uvicorn app.main:app --host 0.0.0.0 --port 8582 --reload

# Or use Docker
docker-compose -f docker-compose.prod.yml up --build -d
```

### 6. Access Control Panel
Open http://localhost:8582 in your browser to access the control panel.

## 🎛️ Control Panel Features

The entire system is managed through a minimal, single-page web UI:

- **System Status** - Real-time monitoring of bot health, costs, and posting activity
- **Persona Configuration** - Edit the bot's personality and voice in real-time
- **Exemplar Tweets** - Manage style guide tweets that influence generation
- **Knowledge Base Explorer** - Search and browse the ingested philosophical content
- **Emergency Controls** - Immediate stop/start capabilities with cost protection
- **Health Monitoring** - API status, error rates, and system metrics

## 🏗️ System Architecture

```mermaid
graph TD
    subgraph 1️⃣  OFF-LINE INGEST PIPELINE
        A[PDFs] --> B(Text Extraction & Clean-up)
        B --> C(Big-Chunk Splitter ~1500 words)
        C --> D(OpenAI Embeddings)
        D --> E[ChromaDB Vector Store]
    end

    subgraph 2️⃣  RUNTIME BOT SERVICE
        E --> F[Random Seed Selector]
        F --> G[Recent Posts Check]
        G -->|not recent| H[Context Retriever k-NN]
        G -->|too recent| F
        I[persona.txt] --> J[Prompt Builder]
        K[exemplars.json] --> J
        H --> J
        J --> L[OpenAI GPT-4/3.5]
        L --> M[Content Filter]
        M --> N[Character Limit Check]
        N -->|>280| O[Tweet Shortener]
        O --> N
        N --> P[Cost/Rate Limit Check]
        P --> Q[Twitter API v2]
        Q --> R[Activity Logger]
    end

    subgraph 3️⃣  WEB UI
        S[Dashboard] --> I
        S --> K
        S --> T[Emergency Stop]
        S --> U[System Health]
    end

    subgraph 4️⃣  ORCHESTRATION
        V[APScheduler] --> F
        W[Cloud Scheduler] --> F
    end
```

## 🔧 Core Components

### 1. **Data Pipeline** (`ingest/`)
- **PDF Processing**: Clean text extraction with artifact removal
- **Large Chunking**: Context-rich segments (1500+ words) to preserve meaning
- **Vector Embeddings**: OpenAI text-embedding-3-small for semantic search
- **ChromaDB Storage**: Local persistence with zero-ops deployment

### 2. **Generation Engine** (`app/generation.py`)**
- **Seed Selection**: Random chunk selection with deduplication
- **Context Retrieval**: k-NN similarity search for thematic coherence  
- **Dynamic Prompting**: Jinja2 templates combining persona + context + exemplars
- **Tweet Refinement**: Auto-shortening and content filtering

### 3. **Multi-Platform Integration**
- **Twitter Client** (`app/twitter_client.py`): Twitter API v2 with rate limiting and error handling
- **Threads Client** (`app/threads_client.py`): Meta's Threads Graph API integration
- **Unified Poster** (`app/multi_platform_poster.py`): Coordinates posting across all platforms
- **Platform Adaptation**: Content optimized for each platform's character limits
- **Test Mode**: Generate without posting for safe development across all platforms

### 4. **Content Safety** (`app/security.py`)**
- **Multi-layer Filtering**: Basic rules + OpenAI moderation API
- **Political Avoidance**: Automatic detection and blocking of controversial topics
- **Profanity Protection**: Configurable word filtering
- **Emergency Controls**: Immediate stop capabilities with audit trails

### 5. **Monitoring & Observability** (`app/monitoring.py`)**
- **Cost Tracking**: Real-time API cost monitoring with daily limits
- **Activity Logging**: Comprehensive posting history with SQLite storage
- **Health Checks**: Automated system health validation
- **Performance Metrics**: Success rates, response times, error analysis

```

### Configuration (`config.yaml`)
```yaml
# Posting schedule with missed runs handling
scheduler:
  enabled: true
  post_interval_hours: 6  # Post every 6 hours (4 times per day)
  timezone: "UTC"
  
  # Catch-up posting for missed runs
  catch_up_enabled: true
  max_catch_up_posts: 3  # Maximum catch-up posts per account on startup
  catch_up_grace_period_hours: 1  # Grace period before considering a post "missed"

# OpenAI API settings
openai:
  model: "gpt-4.1"  # Use gpt-4.1 for creative tasks, or "o3" for complex reasoning
  shortening_model: "gpt-4.1"
  max_tokens: 1000
  temperature: 0.8

# Twitter API settings
twitter:
  post_enabled: true  # Set to false for testing
  character_limit: 280

# Threads API settings
threads:
  post_enabled: true  # Set to false for testing
  character_limit: 500

# Cost management
cost_limits:
  daily_limit_usd: 10.00
  emergency_stop_enabled: true
```

### Secrets (`.env`)
```bash
OPENAI_API_KEY=sk-your-key-here

# Twitter API credentials
TWITTER_BEARER_TOKEN=your-bearer-token
TWITTER_API_KEY=your-api-key
TWITTER_API_SECRET=your-api-secret
TWITTER_ACCESS_TOKEN=your-access-token
TWITTER_ACCESS_TOKEN_SECRET=your-access-token-secret

# Threads API credentials
THREADS_ACCESS_TOKEN=your-threads-access-token
THREADS_USER_ID=your-threads-user-id
```

## 🧪 Testing & Development

### Development Mode
```bash
# Run with auto-reload
uvicorn app.main:app --reload

# Or with Docker
docker-compose -f docker/docker-compose.yml up
```

### Generate Test Content
```bash
# Through the web UI: Use "Generate Test Content" button
# Or via API:
curl -X POST http://localhost:8582/api/test-generation

# For specific account:
curl -X POST http://localhost:8582/api/test-generation/startupquotes

# Test specific platform:
curl -X POST http://localhost:8582/api/force-post-platform/startupquotes/twitter
curl -X POST http://localhost:8582/api/force-post-platform/startupquotes/threads
```

## 🎯 Multi-Platform API Endpoints

### Account Management
```bash
# List all accounts
GET /api/accounts

# Get account status
GET /api/status/{account_id}

# Force post to all platforms for specific account
POST /api/force-post/{account_id}

# Force post to specific platform
POST /api/force-post-platform/{account_id}/{platform}  # platform: twitter|threads

# Test generation for specific account
POST /api/test-generation/{account_id}

# Get platform info for account
GET /api/platform-info/{account_id}

# Test platform connections
GET /api/test-connections/{account_id}

# Search account's knowledge base
GET /api/search-chunks/{account_id}?query=startup
```

### Adding New Accounts
1. **Create account file**: `accounts/mybot.json`
2. **Copy structure** from `accounts/startupquotes.json`
3. **Update configuration**:
   ```json
   {
     "account_id": "mybot",
     "display_name": "My Bot",
     "persona": "Your unique bot personality...",
     "exemplars": [...],
     "vector_collection": "mybot_knowledge",
     "posting_platforms": ["twitter", "threads"],
     "twitter_credentials": {...},
     "threads_credentials": {
       "access_token": "env:THREADS_ACCESS_TOKEN",
       "user_id": "env:THREADS_USER_ID"
     }
   }
   ```
4. **Restart application** - new account automatically included

## 📦 Deployment

### Docker Production
```bash
# Build production image
docker build -f docker/Dockerfile -t twitter-persona-agents .

# Run with environment variables
docker run -d --name twitter-persona-agents \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  twitter-persona-agents
```

### Google Cloud Run
```bash
# Build and push to Container Registry
docker build -f docker/Dockerfile -t gcr.io/PROJECT-ID/twitter-persona-agents .
docker push gcr.io/PROJECT-ID/twitter-persona-agents

# Deploy to Cloud Run
gcloud run deploy twitter-persona-agents \
  --image gcr.io/PROJECT-ID/twitter-persona-agents \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

## 📊 Monitoring & Maintenance

### Health Endpoints
- `GET /health` - Basic health check
- `GET /health/deep` - Comprehensive system validation
- `GET /api/status` - Real-time system status (legacy, single account)
- `GET /api/status/{account_id}` - Account-specific status
- `GET /api/accounts` - List all configured accounts
- `GET /api/platform-info/{account_id}` - Platform-specific account information
- `GET /api/test-connections/{account_id}` - Test all platform connections

### Logs & Metrics
- **Structured Logging**: JSON logs with correlation IDs and account context
- **Activity History**: Complete posting history with metadata per account
- **Multi-Account Monitoring**: Track performance across all accounts
- **Error Analysis**: Failure rates and error categorization per account

### Emergency Procedures
1. **Emergency Stop**: Use red button in web UI or `POST /emergency-stop`
2. **Account-Specific Issues**: Monitor individual account health via `/api/status/{account_id}`
3. **API Failures**: Circuit breakers with exponential backoff per account
4. **Content Issues**: Multi-layer filtering with manual override

## 🔒 Security & Compliance

### Content Safety
- **OpenAI Moderation**: Automatic content screening for all platforms
- **Political Filtering**: Avoids controversial topics across platforms
- **Profanity Protection**: Configurable word filtering
- **Platform Compliance**: Adheres to Twitter and Threads content policies
- **Human Override**: Emergency stop and manual review capabilities

### Data Privacy
- **Local Storage**: All data stored locally (ChromaDB, SQLite)
- **No Data Collection**: No user data or analytics collection
- **Minimal API Calls**: Efficient API usage with caching

### Platform Compliance
- **Rate Limiting**: Respects all Twitter and Threads API limits
- **Clear Attribution**: Bot identification in profiles
- **Terms Compliance**: Follows Twitter and Meta automation rules
- **Cross-Platform Consistency**: Maintains persona across platforms

## 🛠️ Customization

### Account-Specific Customization
Each account is fully customizable via its JSON configuration:

**Persona Tuning**: Edit the `persona` field in `accounts/{account_id}.json`
**Style Examples**: Modify the `exemplars` array for account-specific tweet styles
**Knowledge Base**: Set different `vector_collection` names for account-specific knowledge

### Source Material
Add new PDF books to `data/source_material/` and re-run the ingestion pipeline.

### Prompts
Modify `prompts/base_prompt.j2` and `prompts/shortening_prompt.j2` for custom generation logic.

## 📈 Performance & Costs

### Typical Costs (per post per account)
- **o3 Generation**: ~$0.05-0.15 (reasoning model)
- **GPT-4.1 Generation**: ~$0.02-0.05 (faster alternative)
- **Embeddings**: ~$0.001
- **Moderation**: Free
- **Total**: ~$0.02-0.15 per post per account (same content to all platforms)
- **Daily cost per account**: ~$0.08-0.60 (4 posts at 6-hour intervals to all platforms)

### Performance Metrics
- **Generation Time**: 3-8 seconds average
- **API Success Rate**: >95% with retry logic
- **Memory Usage**: ~200MB base + vector DB size
- **Storage**: ~50MB per book + embeddings

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Run the test suite (`pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Eckhart Tolle** for profound teachings on presence and consciousness
- **Carolyn Elliott** for revolutionary work on shadow integration and existential kink
- The open-source community for the amazing tools that make this possible

## 🐛 Troubleshooting

### Common Issues

**\"No PDF files found\"**
- Ensure PDFs are in `data/source_material/`
- Check file permissions and names

**\"OpenAI API key not found\"**
- Verify `.env` file exists and has correct key
- Check `OPENAI_API_KEY` environment variable

**\"Twitter authentication failed\"**
- Verify all 5 Twitter credentials in `.env`
- Ensure API v2 access is enabled on your Twitter app

**\"Threads authentication failed\"**
- Verify `THREADS_ACCESS_TOKEN` and `THREADS_USER_ID` in `.env`
- Ensure your Threads account has API access enabled

**\"Vector database empty\"**
- Run `python -m ingest.split_embed` to build knowledge base
- Check for errors in PDF processing logs

**\"Account {account_id} not found\"**
- Verify account JSON file exists in `accounts/` directory
- Check account_id matches filename (e.g., `zenkink.json` → `account_id: "zenkink"`)
- Run migration script if upgrading from single-account setup

**\"No catch-up posts scheduled\"**
- Check if `catch_up_enabled: true` in config.yaml
- Verify posts exist in database (check `data/post_history.db`)
- Ensure enough time has passed since last post (> interval + grace period)
- Review logs for "Startup catch-up check completed" messages

**\"Too many catch-up posts\"**
- Adjust `max_catch_up_posts` in config.yaml (default: 3)
- Increase `catch_up_grace_period_hours` to be less aggressive (default: 1)
- Check if multiple accounts are triggering catch-ups simultaneously

### Getting Help
1. Check the logs in `data/logs/`
2. Use the health check endpoints
3. Review configuration files
4. Open an issue on GitHub with logs and config (redacted)

---


## 📋 Multi-Account Architecture

### **Account-Specific Design**
Each account operates independently with its own:
- **Unique personas** and voice characteristics
- **Custom exemplar tweets** for style guidance  
- **Dedicated or shared knowledge bases** (vector collections)
- **Independent Twitter credentials** and rate limiting
- **Account-specific monitoring** and logging

### **Unified Multi-Platform Scheduling**
- **Single scheduler** manages all accounts across all platforms
- **One post per account** per scheduled interval (every 6 hours = 4 posts/day)
- **Simultaneous posting** to all enabled platforms (Twitter + Threads)
- **Missed runs handling** with automatic catch-up posts on startup
- **Parallel processing** for efficient multi-account, multi-platform posting
- **Platform-aware error handling** and retry logic

### **Core Generation Logic** (Per Account)
1. **Random Seed Selection**: Choose random chunk from account's vector collection
2. **Context Retrieval**: Find related chunks using semantic similarity
3. **Style Application**: Apply account's exemplar posts for voice consistency  
4. **Dynamic Prompting**: Combine account persona + context + exemplars
5. **Platform Adaptation**: Optimize content for each platform's character limits
6. **Multi-Platform Posting**: Generate once and post simultaneously to all enabled platforms

### **Key Design Principles**
- **Account Isolation**: Each account's content and style remain distinct across platforms
- **Platform Independence**: Add or remove platforms without affecting others
- **Shared Infrastructure**: Common scheduling, monitoring, and health systems
- **Zero-Configuration Scaling**: Add accounts or platforms by updating JSON files
- **Backward Compatibility**: Legacy single-account endpoints still supported

**Ready to scale your digital presence across multiple accounts and platforms? Let's build something transformative.** 🚀✨