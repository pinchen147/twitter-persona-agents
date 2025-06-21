"""
Dependency injection system - Centralized resource management.

This module provides a centralized dependency injection system that manages
all external resources and configuration for the application. It ensures
consistent access to APIs, databases, and configuration across all modules.

Key Dependencies:
- Configuration: YAML-based settings management
- OpenAI Client: API access for generation and embeddings
- Twitter Client: Account-specific Twitter API access
- Vector Database: ChromaDB client for knowledge storage
- Account Data: Personas, exemplars, and settings

Features:
- Environment variable loading from config/.env
- Account-specific resource isolation
- Backward compatibility with single-account setup
- Graceful fallbacks for missing configurations
- Validation of required credentials

The dependency system enables:
- Clean separation of concerns
- Easy testing with mock dependencies
- Multi-account support with isolated resources
- Configuration validation at startup
- Centralized error handling for missing configs
"""

import os
from pathlib import Path
from typing import Generator

import yaml
from openai import OpenAI
import tweepy
import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv

from app.exceptions import ConfigurationError
from app.account_manager import get_account, load_all_accounts

# Load environment variables from ../../.env
load_dotenv("../../.env")


def get_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = Path("config/config.yaml")
    if not config_path.exists():
        # Try example config for development
        config_path = Path("config/config.example.yaml")
        if not config_path.exists():
            raise ConfigurationError("No configuration file found")
    
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    return config


def get_openai_client() -> OpenAI:
    """Create OpenAI client with API key from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ConfigurationError("OPENAI_API_KEY environment variable not set")
    
    return OpenAI(api_key=api_key)


def get_twitter_client(account_id: str = None) -> tweepy.Client:
    """Create Twitter client with credentials from environment or account config."""
    if account_id:
        # Get credentials from account configuration
        account = get_account(account_id)
        if not account:
            raise ConfigurationError(f"Account not found: {account_id}")
        
        creds = account["twitter_credentials"]
        bearer_token = creds["bearer_token"]
        api_key = creds["api_key"]
        api_secret = creds["api_secret"]
        access_token = creds["access_token"]
        access_token_secret = creds["access_token_secret"]
    else:
        # Fallback to environment variables (for backward compatibility)
        bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
        api_key = os.getenv("TWITTER_API_KEY")
        api_secret = os.getenv("TWITTER_API_SECRET")
        access_token = os.getenv("TWITTER_ACCESS_TOKEN")
        access_token_secret = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
    
    missing_creds = []
    if not bearer_token:
        missing_creds.append("TWITTER_BEARER_TOKEN")
    if not api_key:
        missing_creds.append("TWITTER_API_KEY")
    if not api_secret:
        missing_creds.append("TWITTER_API_SECRET")
    if not access_token:
        missing_creds.append("TWITTER_ACCESS_TOKEN")
    if not access_token_secret:
        missing_creds.append("TWITTER_ACCESS_TOKEN_SECRET")
    
    if missing_creds:
        source = f"account {account_id}" if account_id else "environment"
        raise ConfigurationError(f"Missing Twitter credentials from {source}: {', '.join(missing_creds)}")
    
    return tweepy.Client(
        bearer_token=bearer_token,
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
        wait_on_rate_limit=True
    )


def get_vector_db() -> chromadb.PersistentClient:
    """Create ChromaDB client."""
    config = get_config()
    persist_dir = config.get("vector_db", {}).get("persist_directory", "./data/chroma")
    
    # Ensure directory exists
    Path(persist_dir).mkdir(parents=True, exist_ok=True)
    
    return chromadb.PersistentClient(
        path=persist_dir,
        settings=Settings(anonymized_telemetry=False)
    )


def get_persona(account_id: str = None) -> str:
    """Load persona from account config or fallback to persona.txt file."""
    if account_id:
        # Get persona from account configuration
        account = get_account(account_id)
        if account and "persona" in account:
            return account["persona"]
        raise ConfigurationError(f"Persona not found for account: {account_id}")
    
    # Fallback to file (for backward compatibility)
    persona_path = Path("data/persona.txt")
    if not persona_path.exists():
        raise ConfigurationError("Persona file not found at data/persona.txt")
    
    return persona_path.read_text().strip()


def get_exemplars(account_id: str = None) -> list[dict]:
    """Load exemplar tweets from account config or fallback to exemplars.json file."""
    if account_id:
        # Get exemplars from account configuration
        account = get_account(account_id)
        if account and "exemplars" in account:
            return account["exemplars"]
        raise ConfigurationError(f"Exemplars not found for account: {account_id}")
    
    # Fallback to file (for backward compatibility)
    import json
    
    exemplars_path = Path("data/exemplars.json")
    if not exemplars_path.exists():
        raise ConfigurationError("Exemplars file not found at data/exemplars.json")
    
    with open(exemplars_path) as f:
        exemplars = json.load(f)
    
    return exemplars


def get_vector_collection_name(account_id: str = None) -> str:
    """Get vector collection name from account config or fallback to default."""
    if account_id:
        # Get collection name from account configuration
        account = get_account(account_id)
        if account and "vector_collection" in account:
            return account["vector_collection"]
        raise ConfigurationError(f"Vector collection not found for account: {account_id}")
    
    # Fallback to config file
    config = get_config()
    return config.get("vector_db", {}).get("collection_name", "zen_kink_knowledge")