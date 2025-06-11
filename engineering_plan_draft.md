![Project Status: In Development](https://img.shields.io/badge/status-in_development-yellow)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

Zen Kink Bot is an autonomous Twitter agent designed to generate and post insightful content by synthesizing the philosophies of **Eckhart Tolle** (presence, the ego, the pain-body) and **Carolyn Elliott** (existential kink, shadow work).

The system is built on a core philosophy of **simplicity and ruthless pragmatism**. Its primary purpose is not just to post, but to serve as a platform for easily tuning and evolving a unique digital persona through a minimal, powerful control panel.

### Control Panel

The entire system is managed through a minimal, single-page web UI designed for effortless maintenance and experimentation.

```
+-----------------------------------------------------------------------------+
| Zen Kink Bot - Control Panel                                                |
+-----------------------------------------------------------------------------+
|                                                                             |
| [ SYSTEM STATUS ]                                                           |
|    Status:         ACTIVE & RUNNING ✅                                       |
|    Last Post:      2 hours ago (SUCCESS)                                     |
|    Next Post In:   5 hours 58 minutes                                        |
|    Daily Cost:     $2.43 / $10.00 limit                                     |
|    [ View Activity Log ] [ Force Post Now ] [ 🚨 EMERGENCY STOP ]           |
|                                                                             |
+-----------------------------------------------------------------------------+
|                                                                             |
| [ PERSONA CONFIGURATION ]                                                   |
|    > You are a wise guide who blends the stillness of Eckhart Tolle with    |
|    > the provocative shadow work of Carolyn Elliott. Your voice is calm,    |
|    > direct, and slightly mischievous...                                    |
|    > [__________________________________________________________________]   |
|    [ Save Persona ]  [ Save & Generate Test Tweet (don't post) ]            |
|                                                                             |
+-----------------------------------------------------------------------------+
|                                                                             |
| [ EXEMPLAR TWEETS ] (Style Guide)                                           |
|    + Add New Exemplar: [_________________________________] [Add]            |
|    - "True presence isn't an escape from life, it's a radical acceptance..."|
|                                                                             |
+-----------------------------------------------------------------------------+
|                                                                             |
| [ KNOWLEDGE BASE EXPLORER ]                                                 |
|    Search Chunks: [ the ego________ ] [Search]                              |
|    - Chunk ID: 734 | "The ego is not who you are. The ego is your self-image"|
|                                                                             |
+-----------------------------------------------------------------------------+
|                                                                             |
| [ SYSTEM HEALTH & MONITORING ]                                              |
|    API Status:     OpenAI ✅  Twitter ✅  ChromaDB ✅                          |
|    Error Rate:     0.2% (last 24h)                                          |
|    Content Filter: 3 tweets blocked (last 7 days)                          |
|    [ View Detailed Metrics ] [ Download Logs ] [ Backup Config ]           |
+-----------------------------------------------------------------------------+
```

## High-Level System Architecture (v0.1)

```mermaid
graph TD
    subgraph 1️⃣  OFF-LINE INGEST PIPELINE
        A[PDFs] --> B(Text Extraction & Clean-up)
        B --> C(Big-Chunk Splitter (~1-3 pages))
        C --> D(OpenAI Embedding API)
        D --> |upsert| E(Vector DB – Chroma)
    end

    subgraph 2️⃣  RUNTIME BOT SERVICE  (FastAPI container)
        style P fill:#fff3,stroke:#333,stroke-width:1px
        style G fill:#fff3,stroke:#333,stroke-width:1px
        E -. random seed .-> G(Random Seed Selector)
        G --> R(Recent Posts Check ↣ SQLite)
        R -->|not recent| H(Context Retriever ↣ k-NN)
        R -->|too recent| G
        F[exemplars.json] --> J(Prompt Builder ↣ Jinja2)
        P[persona.txt] --> J
        H --> J
        J --> K(LLM Call ↣ GPT-4/3.5)
        K --> S(Content Filter ↣ OpenAI Moderation)
        S --> L(Char-Count Guard ≤ 280)
        L -->|>280| T(Tweet Shortener ↣ GPT-3.5)
        T --> L
        L --> CB(Cost/Rate Limit Check)
        CB --> M(Twitter Poster ↣ X API v2)
        M --> LOG(Activity Logger)
    end

    subgraph 3️⃣  WEB UI  (HTMX/Tailwind, served by same FastAPI)
        U1(View/Edit persona.txt)
        U2(Add/Delete Exemplars)
        U3(Browse Knowledge Chunks)
        U4(System Health Dashboard)
        U5(Emergency Stop Control)
        U1 --> P
        U2 --> F
        U3 --> E
        U4 --> LOG
        U5 --> CB
    end

    subgraph 4️⃣  ORCHESTRATION
        CS(Cloud Scheduler cron) -->|HTTP ping /run| G
        APS(APScheduler optional) -.-> G
    end

    classDef dashed stroke-dasharray: 5 5;
```

## Technology Stack & Rationale

This stack is chosen for maximum velocity, minimum operational overhead, and easy iteration.

*   **Language:** **Python 3.11+** for its rich NLP ecosystem.
*   **Ingest Pipeline:**
    *   **Text Extraction:** `pdfplumber` + regex for high-quality text cleanup.
    *   **Chunking:** Custom "LargeParagraphSplitter" (≈1500 words).
    *   **Embeddings:** OpenAI `text-embedding-3-small` (cheap, high context).
    *   **Vector DB:** **ChromaDB** on disk for zero-ops, Docker-friendly persistence.
*   **Core Bot Service:**
    *   **Framework:** **FastAPI** for a unified JSON API and server-side rendered UI.
    *   **Scheduling:** **Cloud Scheduler** for statelessness, with optional in-process `APScheduler`.
    *   **Prompting:** **Jinja2** templates (`prompts/base_prompt.j2`) for clean separation of logic and prompts.
    *   **Twitter:** `tweepy` v4+ for Twitter API v2.
*   **Web UI:**
    *   **Interactivity:** **HTMX** for progressive enhancement without a complex frontend build step.
    *   **Styling:** **TailwindCSS** via CDN for clean styling without a `node` toolchain.
*   **Deployment:**
    *   **Container:** **Docker** (Python slim base).
    *   **Hosting:** **Google Cloud Run** for stateless, serverless execution.
    *   **Secrets:** **Google Secret Manager**, mounted as environment variables.
*   **Observability:** `structlog` to structured STDOUT, captured by Cloud Logging.

> **Why these choices?**  
> *   **Social Media Lens:** Quick iteration on persona (`persona.txt`) & exemplars (`exemplars.json`) is 90% of success. Flat files + HTMX editing beat any DB/ORM overhead.
> *   **Engineering Lens:** A single repo, single Docker image, and single process is the easiest path to Cloud Run. All state lives on a disk volume, minimizing managed service dependencies.

## Project Structure

```
zenkink/
 ├─ app/                     # FastAPI application code
 │   ├─ main.py              # entrypoint, health checks
 │   ├─ deps.py              # dependency injection
 │   ├─ scheduler.py         # APScheduler integration
 │   ├─ generation.py        # core tweet generation logic
 │   ├─ twitter_client.py    # Twitter API integration
 │   ├─ monitoring.py        # metrics, logging, alerting
 │   ├─ security.py          # content filtering, validation
 │   └─ exceptions.py        # custom exception handlers
 ├─ ingest/                  # offline data processing
 │   ├─ ingest_pdf.py        # PDF text extraction
 │   ├─ split_embed.py       # chunking and embedding
 │   └─ backup.py            # data backup utilities
 ├─ prompts/                 # prompt templates
 │   ├─ base_prompt.j2       # main generation prompt
 │   └─ shortening_prompt.j2 # tweet shortening prompt
 ├─ ui_templates/            # Jinja2 HTML templates
 │   ├─ dashboard.html       # main control panel
 │   ├─ components/          # HTMX partial templates
 │   └─ static/              # CSS, JS assets
 ├─ tests/                   # comprehensive test suite
 │   ├─ unit/                # unit tests
 │   ├─ integration/         # integration tests
 │   └─ fixtures/            # test data and mocks
 ├─ data/                    # application data
 │   ├─ chroma/              # vector database persistence
 │   ├─ source_material/     # original PDF files
 │   ├─ backups/             # automated backups
 │   ├─ logs/                # local log storage
 │   ├─ exemplars.json       # style guide tweets
 │   ├─ persona.txt          # bot personality prompt
 │   └─ post_history.db      # SQLite: posting history & deduplication
 ├─ config/                  # configuration management
 │   ├─ config.yaml          # application configuration
 │   ├─ config.example.yaml  # example configuration
 │   └─ secrets.env.example  # example secrets file
 ├─ scripts/                 # utility scripts
 │   ├─ deploy.sh            # deployment automation
 │   ├─ backup.sh            # manual backup script
 │   └─ health_check.py      # external health monitoring
 ├─ docker/                  # containerization
 │   ├─ Dockerfile           # production container
 │   ├─ Dockerfile.dev       # development container
 │   └─ docker-compose.yml   # local development stack
 ├─ requirements.txt         # Python dependencies
 ├─ requirements-dev.txt     # development dependencies
 ├─ pytest.ini             # test configuration
 ├─ .github/                # GitHub Actions CI/CD
 │   └─ workflows/
 │       ├─ test.yml         # automated testing
 │       └─ deploy.yml       # deployment pipeline
 └─ README.md               # comprehensive documentation
```

## Getting Started: Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/zen-kink-bot.git
    cd zen-kink-bot
    ```

2.  **Set up environment and install dependencies:**
    *(Assuming Python 3.11+ and pip)*
    ```bash
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3.  **Configure your environment:**
    *   Create a `config.yaml` from the example and edit it.
    *   Create a `.env` file for secrets (API keys), which will be sourced locally and managed by Secret Manager in the cloud.

## Usage

### 1. Build the Knowledge Base (Offline Pipeline)
This is a one-time step per new book.

1.  Place your PDF books inside the `data/source_material/` directory.
2.  Run the ingestion script:
    ```bash
    python -m ingest.ingest_pdf
    ```
    This script will process the PDFs, chunk them, generate embeddings, and load them into the local Chroma database in `./data/chroma/`.

### 2. Run the Application
To run the web UI and the automated posting scheduler locally:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Access the Control Panel at `http://localhost:8000`.

## Error Handling & Resilience Strategy

### API Failure Handling
*   **OpenAI API Failures:** Implement exponential backoff (2^n seconds) with max 3 retries. Fallback to cheaper model (gpt-3.5-turbo) if GPT-4 fails.
*   **Twitter API Failures:** Respect rate limits (300 tweets/3hrs). Implement 15-minute retry with jitter. Store failed tweets in SQLite for manual review.
*   **Embedding API Failures:** Cache embeddings locally. Implement batch retry for failed chunks.

### Circuit Breaker Pattern
*   **Cost Protection:** Stop execution if daily OpenAI costs exceed $5 threshold.
*   **Rate Limit Protection:** Pause posting if Twitter rate limit hit, resume after reset window.
*   **Quality Control:** Stop posting if 3 consecutive tweets fail character limit after shortening.

### Data Integrity
*   **Vector DB Corruption:** Daily backup of ChromaDB to Cloud Storage. Implement health check endpoint.
*   **Config Validation:** Validate persona.txt and exemplars.json on startup. Reject invalid configurations.
*   **Graceful Degradation:** If vector search fails, fall back to random chunk selection.

## Security & Compliance

### API Security
*   **Secrets Management:** All API keys in Google Secret Manager with automatic rotation alerts.
*   **Principle of Least Privilege:** Twitter API keys limited to tweet-only permissions.
*   **Network Security:** Cloud Run configured with ingress controls, HTTPS-only.

### Content Safety
*   **Content Filtering:** Implement OpenAI moderation API check before posting.
*   **Profanity Filter:** Simple regex filter for obvious problematic content.
*   **Human Override:** Emergency "pause bot" feature in UI for immediate shutdown.

### Twitter Compliance
*   **Automation Rules:** Clear bot identification in Twitter bio. Respect 300 tweets/3 hours limit.
*   **Rate Limiting:** Built-in Twitter API rate limit respect with exponential backoff.
*   **Content Attribution:** All tweets include subtle attribution to source philosophy when possible.

## Testing Strategy

### Unit Testing
*   **Generation Pipeline:** Mock OpenAI responses, test prompt building, context retrieval.
*   **Text Processing:** Test PDF extraction, chunking, cleanup with sample documents.
*   **Twitter Integration:** Mock Twitter API responses, test posting logic.

### Integration Testing
*   **End-to-End Flow:** Test complete pipeline from seed selection to tweet generation (without posting).
*   **API Integration:** Test against real APIs in staging environment with test accounts.
*   **UI Testing:** Test HTMX interactions, form submissions, file uploads.

### Production Testing
*   **Staging Environment:** Mirror production setup with test Twitter account.
*   **Canary Deployment:** Deploy to staging, run 24 hours, monitor before production.
*   **Load Testing:** Simulate multiple concurrent requests to `/run` endpoint.

## Production Readiness & Monitoring

### Cold Start Mitigation
*   **Warm-up Endpoint:** `/health` endpoint for Cloud Scheduler to keep container warm.
*   **Minimum Instances:** Set Cloud Run min instances to 1 during active hours.
*   **Timeout Configuration:** Set generous timeout (5 minutes) for `/run` endpoint.

### Observability
*   **Structured Logging:** `structlog` with correlation IDs for request tracing.
*   **Metrics Collection:** Track API call counts, costs, success rates, response times.
*   **Alerting:** Google Cloud Monitoring alerts for failures, high costs, API errors.

### Health Monitoring
*   **Endpoint Health:** `/health` checks ChromaDB connection, file system access.
*   **Business Logic Health:** `/health/deep` validates persona.txt exists, exemplars loadable.
*   **External Dependencies:** Monitor OpenAI API status, Twitter API status.

## Cost Management & Optimization

### Cost Monitoring
*   **Usage Analytics:** Track tweets generated, API calls made, success rates.

### Circuit Breakers
*   **Daily Spend Limit:** Hard stop at $10/day spend across all APIs.
*   **Request Rate Limiting:** Max 50 OpenAI calls per hour during generation.
*   **Emergency Shutdown:** UI button to immediately disable all automated posting.

## Enhanced Pitfalls & Mitigations

### Data Quality Issues
1.  **PDF Garbage (headers/footers):** Regex stripping + heuristics (remove >35% identical lines across pages).
2.  **Poor Text Extraction:** Fallback to `PyPDF2` if `pdfplumber` fails. Manual review for critical books.
3.  **Embedding Drift:** Version control embeddings. Re-embed if OpenAI updates embedding models.

### Generation Quality Issues
1.  **Tweets > 280 Chars:** Post-LLM guard with second call: "shorten this to 240 characters."
2.  **Repetitive Content:** SQLite log of seed chunk hashes for last 50 posts. Re-draw if recently used.
3.  **Off-brand Content:** Implement content scoring against exemplars. Reject if similarity < 0.7.

### Infrastructure Issues
1.  **Cloud Run Cold Starts:** Retry window ≥1 minute. Idempotent `/run` endpoint design.
2.  **Vector DB Corruption:** Daily ChromaDB backup to Cloud Storage. Health check validation.
3.  **Config File Corruption:** Validate on startup. Backup persona.txt and exemplars.json to Cloud Storage.

### API & External Dependencies
1.  **OpenAI API Changes:** Pin to specific API version. Monitor for deprecation notices.
2.  **Twitter API Changes:** Use official `tweepy` library. Monitor Twitter developer announcements.
3.  **Rate Limit Exhaustion:** Implement exponential backoff. Store failed requests for retry.

### Security & Content Issues
1.  **Inappropriate Content:** OpenAI moderation API check. Human review flag for edge cases.
2.  **API Key Exposure:** Secrets in Secret Manager only. No keys in code/config files.
3.  **Unauthorized Access:** Cloud Run IAM properly configured. No public endpoints except health check.

## Development Workflow & Deployment

### Local Development
1.  **Environment Setup:** Python 3.11+, virtual environment, `.env` for local secrets.
2.  **Development Mode:** `uvicorn --reload` with debug logging, mock Twitter API.
3.  **Testing:** `pytest` for unit tests, `docker-compose` for integration tests.

### CI/CD Pipeline
1.  **GitHub Actions:** Run tests, build Docker image, push to Google Container Registry.
2.  **Staging Deployment:** Auto-deploy to Cloud Run staging on `main` branch.
3.  **Production Deployment:** Manual approval gate, deploy to production Cloud Run.

### Deployment Architecture
*   **Cloud Run Service:** Stateless container with mounted persistent volume for ChromaDB.
*   **Cloud Scheduler:** Triggers `/run` endpoint every 8 hours (configurable).
*   **Secret Manager:** Stores all API keys, database credentials.
*   **Cloud Storage:** Backup location for ChromaDB, persona.txt, exemplars.json.

## Revised 10-Day Sprint Plan

### Phase 1: Foundation (Days 1-3)
*   **Day 1:** Scaffold repo, Dockerfile, FastAPI "hello world," basic error handling.
*   **Day 2:** Implement `ingest/` scripts with error handling; load first book; verify Chroma queries.
*   **Day 3:** Build `generation.py` pipeline with Jinja2 template, content filtering (console output).

### Phase 2: Core Features (Days 4-6)
*   **Day 4:** Implement Twitter posting + 280-char guard + retry logic; prove manual `/run` works.
*   **Day 5:** Build HTMX UI for persona/exemplars editing with validation.
*   **Day 6:** Add comprehensive logging, health checks, cost tracking.

### Phase 3: Production Ready (Days 7-10)
*   **Day 7:** Implement circuit breakers, backup strategies, monitoring.
*   **Day 8:** Add testing suite, staging environment setup.
*   **Day 9:** Push to Cloud Run, configure secrets, wire Cloud Scheduler.
*   **Day 10:** End-to-end testing, first live automated post, monitoring validation.

### Success Criteria
- [ ] Bot posts autonomously every 8 hours without manual intervention
- [ ] Web UI allows real-time persona and exemplar editing
- [ ] System handles API failures gracefully with proper retries
- [ ] Cost monitoring prevents runaway spending
- [ ] Content filtering prevents inappropriate posts
- [ ] Full observability with logs, metrics, and alerts
