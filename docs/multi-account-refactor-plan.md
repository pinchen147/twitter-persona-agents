# Multi-Account Twitter Agent Refactoring Plan

## Overview
Transform the single-account Twitter bot into a multi-account system where each account is defined by a JSON configuration file containing persona, exemplars, credentials, and settings.

## Goals
- Support multiple Twitter accounts simultaneously
- One tweet per account when scheduler triggers
- Account-specific personas, exemplars, and vector collections
- Separate dashboard views per account
- Unified scheduler and model configuration for simplicity
- Remove cost tracking to simplify codebase

## Phase 1: Account Configuration Foundation

### 1. Create Account Structure
- Create `accounts/` directory
- Create `accounts/startupquotes.json` with current persona, exemplars, and placeholder credentials
- Define account JSON schema and validation

### 2. Account Manager Module
- Create `app/account_manager.py` to handle account loading/management
- Functions: `load_all_accounts()`, `get_account(account_id)`, `validate_account_config()`

## Phase 2: Core Dependency Refactoring  

### 3. Update Dependencies System
- Modify `app/deps.py` to be account-aware
- Add functions: `get_account_persona(account_id)`, `get_account_exemplars(account_id)`, `get_account_twitter_client(account_id)`
- Keep fallback to current files during transition

### 4. Vector Database Multi-tenancy
- Update `app/vector_search.py` to accept `collection_name` parameter
- Modify `VectorSearcher.__init__()` to take collection name
- Update all vector search functions to use account-specific collections

## Phase 3: Generation & Posting Updates

### 5. Tweet Generation Refactor
- Update `app/generation.py` to accept `account_id` parameter
- Modify `TweetGenerator` to work with account-specific data
- Update generation functions: `generate_and_post_tweet(account_id)`, `generate_test_tweet(account_id)`

### 6. Twitter Client Updates
- Update `app/twitter_client.py` to work with account-specific credentials
- Modify `TwitterPoster` to accept account config
- Update posting functions to use account context

## Phase 4: Scheduler Multi-Account Support

### 7. Scheduler Refactor
- Update `app/scheduler.py` to loop through all accounts
- Modify posting logic: for each trigger, post one tweet from each account
- Update error handling to be account-aware

## Phase 5: API & Dashboard Updates

### 8. API Endpoints Refactor
- Add account parameter to all relevant endpoints
- Update routes: `/`, `/api/force-post/{account_id}`, `/api/status/{account_id}`
- Add account listing endpoint: `/api/accounts`

### 9. Dashboard Multi-Account UI
- Add account tabs/navigation to dashboard
- Create account-specific views for status, posts, controls
- Update templates to show current account context

## Phase 6: Monitoring & Cleanup

### 10. Activity Logging Updates
- Update `app/monitoring.py` to include account context in logs
- Remove cost tracking components (CostTracker, cost-related endpoints)
- Keep ActivityLogger and HealthChecker, make them account-aware

### 11. Configuration Cleanup
- Remove cost-related config from `config.example.yaml`
- Update health checks to work across accounts
- Clean up unused cost management code

## Phase 7: Migration & Testing

### 12. Migration Script
- Create script to populate `accounts/startupquotes.json` from existing files
- Preserve current data (persona.txt, exemplars.json)
- Add validation for account configurations

### 13. Testing & Validation
- Test single account functionality (startupquotes)
- Verify dashboard shows account-specific data
- Test force posting for specific accounts
- Ensure scheduler works with account loop

## Account Configuration Schema

```json
{
  "account_id": "startupquotes",
  "display_name": "Startup Wisdom Bot", 
  "persona": "You are Startup Oracle—a no-BS founder-guide who knows great tech is table stakes...",
  "exemplars": [
    {
      "id": 1,
      "text": "The best startups almost always start as side projects...",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "vector_collection": "startup_knowledge",
  "twitter_credentials": {
    "api_key": "your-api-key",
    "api_secret": "your-api-secret", 
    "access_token": "your-access-token",
    "access_token_secret": "your-access-token-secret",
    "bearer_token": "your-bearer-token"
  }
}
```

## Key Implementation Notes

- Keep existing file structure as fallback during transition
- Maintain backward compatibility where possible
- Focus on clean account abstraction without over-engineering
- Remove cost tracking to simplify codebase
- All accounts share same global config (model, schedule, etc.)
- Each account gets separate dashboard tab/view
- Scheduler posts one tweet per account on each trigger
- Vector collections can be shared between accounts if desired

## Directory Structure After Refactor

```
accounts/
  startupquotes.json
  future_account.json
app/
  account_manager.py  # NEW
  deps.py            # UPDATED
  generation.py      # UPDATED
  main.py           # UPDATED
  monitoring.py     # UPDATED (cost tracking removed)
  scheduler.py      # UPDATED
  twitter_client.py # UPDATED
  vector_search.py  # UPDATED
data/
  chroma/           # existing vector db
  logs/             # existing logs
  persona.txt       # kept as fallback
  exemplars.json    # kept as fallback
```

## Success Criteria

1. ✅ Current startupquotes account functionality preserved
2. ✅ Clean account abstraction layer implemented
3. ✅ Dashboard shows account-specific data
4. ✅ Scheduler posts to all accounts
5. ✅ Vector collections work per account
6. ✅ Cost tracking removed
7. ✅ Easy to add new accounts by creating JSON files