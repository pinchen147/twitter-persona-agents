### **Project Handoff: Autonomous Twitter Bot 

#### **1. Goal**

The primary goal is to design and build a fully autonomous system that generates and posts tweets to a dedicated Twitter account. The system's "mind" will be a synthesis of the philosophies of Eckhart Tolle and Carolyn Elliott. It must be designed from the ground up for **simplicity and rapid experimentation**, particularly around the bot's persona. The final product will be a self-running agent configurable via a minimal web UI. And running on docker (and then on google cloud run)

#### **2. Return Format (The Deliverables)**

The project is complete when the following components are delivered in a single Git repository:

1.  **Data Processing Pipeline:** A set of scripts that can:
    *   Ingest PDF books.
    *   Extract clean text.
    *   Chunk text into large, context-rich segments (multiple paragraphs or chapters).
    *   Generate vector embeddings for each chunk.
    *   Load the chunks and their embeddings into a vector database.

2.  **Core Application:** The main application logic that includes:
    *   A **scheduler** (e.g., cron-based) to trigger tweet generation at a configurable interval (default: every 8 hours).
    *   A **generation engine** that executes the core logic: selects a seed, retrieves context, builds a prompt, calls an LLM, and produces a tweet.
    *   A **Twitter poster** that securely connects to the Twitter API and posts the generated content.

3.  **Simple Web UI:** A minimal front-end that allows a non-technical user to:
    *   View and edit the core **persona prompt**.
    *   Add/view/delete **exemplar tweets** from a simple file.
    *   Browse the text chunks in the knowledge base.

4.  **Configuration:**
    *   A clear `config.yaml` or `.env` file to manage secrets (API keys) and key parameters (posting schedule, LLM model name, vector DB connection info).

5.  **Documentation:**
    *   A `README.md` file explaining the project architecture, setup instructions, how to run the data pipeline, and how to start the application and UI.

#### **3. Warnings (Key Principles & Pitfalls to Avoid)**

*   **Prioritize Simplicity Over Complexity:** This is the most important principle. Do not over-engineer. For example, the exemplar tweets will be stored in a simple `JSON` or markdown file, *not* a database. Start with the most straightforward implementation for every component.
*   **Manage API Costs:** LLM APIs (like OpenAI) and the Twitter API have costs and rate limits. Ensure the application is efficient with its calls. The LLM model used should be easily configurable, allowing for cheaper models during development and testing.
*   **Garbage In, Garbage Out (GIGO):** The quality of the final tweets depends heavily on the quality of the text extracted from the PDFs. Spend adequate time ensuring the text extraction is clean and removes artifacts like page numbers, headers, and footers.
*   **Avoid the "Perfect Prompt" Trap:** The goal is not to find one perfect, static prompt. The goal is to build a system that makes it **easy to experiment** with the prompt. The persona configuration in the UI is a critical feature, not an afterthought.
*   **Twitter API Rules:** Be mindful of Twitter's terms of service and API usage policies to avoid getting the account rate-limited or suspended. Implement basic error handling and logging for API interactions.

#### **4. Relevant Context (The "Why" Behind the Plan)**

*   **Philosophical Source Material:** The knowledge base will be built from the works of **Eckhart Tolle** (*The Power of Now*, etc.) and **Carolyn Elliott** (*Existential Kink*). The desired voice is a blend of their core concepts: presence, ego-dissolution, and shadow work.
*   **Reference Architecture:** The existing project `https://github.com/llj0824/longevity_agent` is a good model for the desired level of simplicity, code structure, and maintainability.
*   **Core Generation Logic Flow:** We have decided on the following simple, fully-automated flow:
    1.  **Random Seed:** The process begins by selecting a **random text chunk** from the vector database.
    2.  **Context Retrieval:** Using the seed chunk's embedding, perform a vector similarity search to find other thematically related chunks.
    3.  **Style Retrieval:** Select a few exemplar tweets from the flat file to guide the style.
    4.  **Dynamic Prompt Generation:** Construct a prompt for an LLM that includes the persona, the retrieved context chunks, and the style exemplars.
    5.  **Post:** Send the generated tweet to Twitter.
*   **Key Design Decisions Already Made:**
    *   **Chunking Strategy:** We prefer **large chunks** to preserve as much context as possible.
    *   **Voice Blending:** For V1, all source texts will be mixed into a **single, unified knowledge base**. We will not tag chunks by author.
    *   **Quality Control:** The system will be **100% automated**. There will be no human review step before a tweet is posted. Quality is controlled by refining the persona and exemplars over time via the UI.

