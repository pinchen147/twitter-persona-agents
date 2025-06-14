# Multi-Account Twitter Agent 🧘✨

![Project Status: Production Ready](https://img.shields.io/badge/status-production_ready-brightgreen)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python: 3.11+](https://img.shields.io/badge/python-3.11+-blue)
![Multi-Account Support](https://img.shields.io/badge/multi--account-supported-orange)

A **multi-account autonomous Twitter agent** that generates and posts insightful content by synthesizing philosophical teachings. Originally designed to blend **Eckhart Tolle** (presence, mindfulness, ego-dissolution) and **Carolyn Elliott** (existential kink, shadow work), the system now supports unlimited Twitter accounts with unique personas.

The system is built on a core philosophy of **simplicity and ruthless pragmatism**. Each account can have its own personality, knowledge base, and posting style, managed through a unified control panel.

## ⚡ Ready to Run

**The environment is already set up!** Just follow these steps:

1. **Activate virtual environment**: `source venv/bin/activate`
2. **Add API keys**: Copy `config/secrets.env.example` to `config/.env` and add your keys
3. **Run migration**: `python scripts/migrate_to_multi_account.py` 
4. **Add PDF books**: Place them in `data/source_material/`
5. **Build knowledge base**: `python -m ingest.split_embed`
6. **Start application**: `uvicorn app.main:app --host 0.0.0.0 --port 8582 --reload`
7. **Open control panel**: http://localhost:8582

## 🔄 Multi-Account Features

### **Account Management**
- **Multiple Twitter accounts** posting simultaneously
- **Account-specific personas** and exemplar tweets  
- **Shared or separate knowledge bases** per account
- **Unified scheduler** posts one tweet per account
- **Easy account addition** via JSON configuration files

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Docker (optional but recommended)
- OpenAI API key
- Twitter API v2 credentials (Bearer token, API keys, Access tokens)

### 1. Clone and Setup
```bash
git clone <your-repo-url>
cd zenkink-twitter-agent

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
docker-compose up --build
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

### 3. **Twitter Integration** (`app/twitter_client.py`)**
- **Rate Limiting**: Respects Twitter API limits with exponential backoff
- **Error Handling**: Comprehensive retry logic and status tracking
- **Test Mode**: Generate without posting for safe development

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

### Secrets (`.env`)
```bash
OPENAI_API_KEY=sk-your-key-here
TWITTER_BEARER_TOKEN=your-bearer-token
TWITTER_API_KEY=your-api-key
TWITTER_API_SECRET=your-api-secret
TWITTER_ACCESS_TOKEN=your-access-token
TWITTER_ACCESS_TOKEN_SECRET=your-access-token-secret
```

## 🧪 Testing & Development

### Development Mode
```bash
# Run with auto-reload
uvicorn app.main:app --reload

# Or with Docker
docker-compose -f docker/docker-compose.yml up
```

### Generate Test Tweet
```bash
# Through the web UI: Use "Generate Test Tweet" button
# Or via API:
curl -X POST http://localhost:8582/api/test-generation

# For specific account:
curl -X POST http://localhost:8582/api/test-generation/zenkink
```

## 🎯 Multi-Account API Endpoints

### Account Management
```bash
# List all accounts
GET /api/accounts

# Get account status
GET /api/status/{account_id}

# Force post for specific account
POST /api/force-post/{account_id}

# Test generation for specific account
POST /api/test-generation/{account_id}

# Search account's knowledge base
GET /api/search-chunks/{account_id}?query=presence
```

### Adding New Accounts
1. **Create account file**: `accounts/mybot.json`
2. **Copy structure** from `accounts/zenkink.json`
3. **Update configuration**:
   ```json
   {
     "account_id": "mybot",
     "display_name": "My Bot",
     "persona": "Your unique bot personality...",
     "exemplars": [...],
     "vector_collection": "mybot_knowledge",
     "twitter_credentials": {...}
   }
   ```
4. **Restart application** - new account automatically included

## 📦 Deployment

### Docker Production
```bash
# Build production image
docker build -f docker/Dockerfile -t zenkink-bot .

# Run with environment variables
docker run -d --name zenkink-bot \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  zenkink-bot
```

### Google Cloud Run
```bash
# Build and push to Container Registry
docker build -f docker/Dockerfile -t gcr.io/PROJECT-ID/zenkink-bot .
docker push gcr.io/PROJECT-ID/zenkink-bot

# Deploy to Cloud Run
gcloud run deploy zenkink-bot \
  --image gcr.io/PROJECT-ID/zenkink-bot \
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
- **OpenAI Moderation**: Automatic content screening
- **Political Filtering**: Avoids controversial topics
- **Profanity Protection**: Configurable word filtering
- **Human Override**: Emergency stop and manual review capabilities

### Data Privacy
- **Local Storage**: All data stored locally (ChromaDB, SQLite)
- **No Data Collection**: No user data or analytics collection
- **Minimal API Calls**: Efficient API usage with caching

### Twitter Compliance
- **Rate Limiting**: Respects all Twitter API limits
- **Clear Attribution**: Bot identification in profile
- **Terms Compliance**: Follows Twitter automation rules

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

### Typical Costs (per tweet per account)
- **o3 Generation**: ~$0.05-0.15 (reasoning model)
- **GPT-4.1 Generation**: ~$0.02-0.05 (faster alternative)
- **Embeddings**: ~$0.001
- **Moderation**: Free
- **Total**: ~$0.02-0.15 per tweet per account

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

**\"Vector database empty\"**
- Run `python -m ingest.split_embed` to build knowledge base
- Check for errors in PDF processing logs

**\"Account {account_id} not found\"**
- Verify account JSON file exists in `accounts/` directory
- Check account_id matches filename (e.g., `zenkink.json` → `account_id: "zenkink"`)
- Run migration script if upgrading from single-account setup

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

### **Unified Scheduling**
- **Single scheduler** manages all accounts
- **One tweet per account** per scheduled interval
- **Parallel processing** for efficient multi-account posting
- **Account-aware error handling** and retry logic

### **Core Generation Logic** (Per Account)
1. **Random Seed Selection**: Choose random chunk from account's vector collection
2. **Context Retrieval**: Find related chunks using semantic similarity
3. **Style Application**: Apply account's exemplar tweets for voice consistency  
4. **Dynamic Prompting**: Combine account persona + context + exemplars
5. **Multi-Account Posting**: Generate and post simultaneously across accounts

### **Key Design Principles**
- **Account Isolation**: Each account's content and style remain distinct
- **Shared Infrastructure**: Common scheduling, monitoring, and health systems
- **Zero-Configuration Scaling**: Add accounts by creating JSON files
- **Backward Compatibility**: Legacy single-account endpoints still supported

**Ready to scale your digital presence across multiple accounts? Let's build something transformative.** 🚀✨