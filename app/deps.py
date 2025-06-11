"""Dependency injection for the FastAPI application."""

import os
from pathlib import Path
from typing import Generator

import yaml
from openai import OpenAI
import tweepy
import chromadb
from chromadb.config import Settings

from app.exceptions import ConfigurationError


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


def get_twitter_client() -> tweepy.Client:
    """Create Twitter client with credentials from environment."""
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
        raise ConfigurationError(f"Missing Twitter credentials: {', '.join(missing_creds)}")
    
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


def get_persona() -> str:
    """Load persona from persona.txt file."""
    persona_path = Path("data/persona.txt")
    if not persona_path.exists():
        raise ConfigurationError("Persona file not found at data/persona.txt")
    
    return persona_path.read_text().strip()


def get_exemplars() -> list[dict]:
    """Load exemplar tweets from exemplars.json file."""
    import json
    
    exemplars_path = Path("data/exemplars.json")
    if not exemplars_path.exists():
        raise ConfigurationError("Exemplars file not found at data/exemplars.json")
    
    with open(exemplars_path) as f:
        exemplars = json.load(f)
    
    return exemplars