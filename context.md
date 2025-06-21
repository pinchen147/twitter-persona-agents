# Twitter Persona Agents - Application Context

## Overview

Twitter Persona Agents is a sophisticated multi-account autonomous Twitter bot system that generates and posts insightful content by synthesizing knowledge from ingested materials. Originally designed for philosophical content, the system now powers startup wisdom bots that share insights from Paul Graham, Y Combinator luminaries, and tech visionaries like Elon Musk, Sam Altman, and Brian Chesky. The system supports unlimited Twitter accounts, each with unique personas and knowledge bases.

## Core Philosophy

The system is built on principles of:
- **Simplicity**: Clean, maintainable code with minimal dependencies
- **Pragmatism**: Focus on what works, avoid over-engineering
- **Autonomy**: Fully automated posting with minimal human intervention
- **Safety**: Multi-layer content filtering and emergency controls
- **Scalability**: Easy addition of new accounts without code changes

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        Web Dashboard                        │
│                    (FastAPI + Jinja2)                       │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                     Core Application                        │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐     │
│  │  Scheduler  │  │  Generation  │  │ Account Manager │     │
│  │(APScheduler)│  │   Engine     │  │  (Multi-Account)│     │
│  └─────────────┘  └──────────────┘  └─────────────────┘     │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐     │
│  │  Monitoring │  │   Security   │  │ Twitter Client  │     │
│  │  (SQLite)   │  │  (Filtering) │  │   (Tweepy)      │     │
│  └─────────────┘  └──────────────┘  └─────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Knowledge Base Layer                     │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐     │
│  │Vector Search│  │   ChromaDB   │  │  Ingestion      │     │
│  │ (Semantic)  │  │ (Embeddings) │  │  Pipeline       │     │
│  └─────────────┘  └──────────────┘  └─────────────────┘     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    External Services                        │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐     │
│  │  OpenAI API │  │ Twitter API  │  │  PDF Books      │     │
│  │ (GPT-4/o3)  │  │     (v2)     │  │  (Source)       │     │
│  └─────────────┘  └──────────────┘  └─────────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. Web Interface (`app/main.py`)
- **Purpose**: FastAPI web server providing dashboard and API endpoints
- **Features**:
  - Real-time monitoring dashboard
  - Account management UI
  - Manual tweet generation
  - System health checks
  - Emergency stop controls
- **Endpoints**:
  - `/` - Main dashboard
  - `/api/accounts` - List all accounts
  - `/api/force-post/{account_id}` - Manual posting
  - `/api/status/{account_id}` - Account status
  - `/health` - System health checks

### 2. Account Management (`app/account_manager.py`)
- **Purpose**: Manages multiple Twitter account configurations
- **Features**:
  - Dynamic account loading from JSON files
  - Configuration validation
  - Credential security
  - Hot-reload on file changes
- **Account Structure**:
  ```json
  {
    "account_id": "unique_id",
    "display_name": "Bot Name",
    "persona": "Personality description",
    "exemplars": ["Example tweets"],
    "vector_collection": "knowledge_base_name",
    "twitter_credentials": {...}
  }
  ```

### 3. Scheduler (`app/scheduler.py`)
- **Purpose**: Automated posting at regular intervals
- **Features**:
  - Posts every 6 hours (4 tweets/day per account)
  - Catch-up system for missed posts
  - Parallel multi-account posting
  - Health monitoring integration
- **Catch-up Logic**:
  - Detects missed posting windows on startup
  - Schedules up to 3 catch-up posts per account
  - 30-second spacing between catch-up posts
  - 1-hour grace period before considering posts "missed"

### 4. Generation Engine (`app/generation.py`)
- **Purpose**: AI-powered tweet content creation
- **Pipeline**:
  1. Random seed selection from knowledge base
  2. Semantic search for related content
  3. Prompt construction with persona + context
  4. AI generation (GPT-4 or o3)
  5. Automatic shortening if needed
  6. Content safety filtering
- **Model Support**:
  - GPT-4/GPT-4.1: Fast creative generation
  - o3/o3-mini: Advanced reasoning for complex insights

### 5. Vector Search (`app/vector_search.py`)
- **Purpose**: Semantic knowledge retrieval
- **Features**:
  - Random chunk selection with deduplication
  - k-NN similarity search
  - Account-specific collections
  - Recent content tracking
- **Process**:
  - Embeds search queries
  - Finds similar philosophical content
  - Returns context for generation

### 6. Security (`app/security.py`)
- **Purpose**: Content safety and system protection
- **Layers**:
  - Profanity filtering
  - Political content avoidance
  - Violence/hate speech detection
  - OpenAI Moderation API
  - Emergency stop triggers
- **Emergency Conditions**:
  - Cost limit exceeded
  - Low success rate (<50%)
  - High error rates

### 7. Monitoring (`app/monitoring.py`)
- **Purpose**: System observability and metrics
- **Components**:
  - **CostTracker**: API spending limits
  - **ActivityLogger**: Tweet history and events
  - **HealthChecker**: System validation
- **Storage**: SQLite database for persistence
- **Metrics**: Success rates, costs, performance

### 8. Twitter Client (`app/twitter_client.py`)
- **Purpose**: Twitter API v2 integration
- **Features**:
  - Account-specific clients
  - Rate limit management
  - Comprehensive error handling
  - Test mode for development
- **Rate Limiting**: 1-minute minimum between posts

### 9. Data Pipeline (`ingest/`)
- **Purpose**: Convert source materials to searchable knowledge base
- **Components**:
  - `ingest_pdf.py`: PDF text extraction and cleaning
  - `split_embed.py`: Chunking and embedding generation
  - `ingest_startup_quotes.py`: Text file processing for startup wisdom
- **Process**:
  1. Extract text from PDFs or text files
  2. Clean artifacts and normalize
  3. Split into chunks (800 words for quotes, 1500 for books)
  4. Generate embeddings via OpenAI
  5. Store in ChromaDB

### 10. Dependencies (`app/deps.py`)
- **Purpose**: Centralized resource management
- **Manages**:
  - Configuration loading
  - API client creation
  - Database connections
  - Account-specific resources

## Data Flow

### Tweet Generation Flow
```
1. Scheduler triggers posting job
2. For each account:
   a. Select random knowledge chunk
   b. Find similar chunks via vector search
   c. Load account persona and exemplars
   d. Build prompt with Jinja2 template
   e. Generate tweet via OpenAI API
   f. Validate and filter content
   g. Post to Twitter
   h. Log results
```

### Knowledge Ingestion Flow
```
1. Place source materials in data/source_material/
   - PDFs for books/essays
   - Text files for quotes/wisdom
2. Run appropriate ingester:
   - python -m ingest.split_embed (for PDFs)
   - python -m ingest.ingest_startup_quotes (for text files)
3. Text extraction → Cleaning → Chunking → Embeddings
4. Embeddings → ChromaDB storage (account-specific collections)
```

## Configuration

### Main Config (`config/config.yaml`)
```yaml
scheduler:
  post_interval_hours: 6
  catch_up_enabled: true
  max_catch_up_posts: 3

openai:
  model: "gpt-4.1"  # or "o3"
  temperature: 0.8

cost_limits:
  daily_limit_usd: 10.00
```

### Environment Variables (`config/.env`)
```
OPENAI_API_KEY=sk-...
TWITTER_BEARER_TOKEN=...
TWITTER_API_KEY=...
```

### Account Files (`accounts/{account_id}.json`)
Each account has its own JSON configuration with persona, exemplars, and credentials.

## Key Design Decisions

1. **Flexible Chunk Sizes**: 800 words for quotes/insights, 1500 for essays - optimized for content type
2. **Account Isolation**: Each account operates independently with its own resources
3. **Catch-up Posts**: Ensures consistent presence even after downtime
4. **Multi-layer Safety**: Combines rule-based and AI-based content filtering
5. **Local Storage**: ChromaDB and SQLite for zero-dependency deployment

## Adding New Accounts

1. Create `accounts/newbot.json` with account configuration
2. Add Twitter credentials and persona
3. Optionally create new vector collection for isolated knowledge
4. Restart application - account automatically included

## Monitoring & Maintenance

- **Dashboard**: http://localhost:8582 for real-time monitoring
- **Logs**: Structured JSON logs with correlation IDs
- **Database**: SQLite at `data/post_history.db`
- **Backups**: Automatic daily backups of activity data

## Security Considerations

- Credentials stored in account JSON files (ensure proper file permissions)
- Content filtering prevents inappropriate posts
- Cost limits prevent runaway API spending
- Emergency stop for immediate shutdown
- Rate limiting prevents Twitter API abuse

## Performance Characteristics

- **Tweet Generation**: 3-8 seconds average
- **API Costs**: $0.02-0.15 per tweet (model dependent)
- **Memory Usage**: ~200MB base + vector DB size
- **Posting Schedule**: 4 tweets/day per account (configurable)

## Future Enhancements

- Web-based account creation UI
- Analytics dashboard with engagement metrics
- Dynamic persona evolution based on performance
- Real-time trend integration for timely startup insights
- Thread generation for deeper dives into topics
- Image quote cards with startup wisdom
- Integration with startup news APIs
- Automated hashtag optimization

---

This system represents a production-ready, scalable solution for managing multiple AI-powered Twitter personalities with sophisticated content generation and safety controls. 