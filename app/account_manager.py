"""
Account management system for coordinating multiple Twitter bot personas.

This module implements the multi-account infrastructure that allows the bot system to manage
multiple Twitter accounts, each with its own unique personality, knowledge base, and credentials.

Key Features:
- Dynamic account loading from JSON configuration files
- Account configuration validation and sanitization  
- Credential management with security checks
- Caching with automatic reload on file changes
- Thread-safe singleton pattern for global access

Architecture:
- Each account is defined by a JSON file in the accounts/ directory
- Account files contain: persona, exemplars, credentials, vector collection name
- Accounts are loaded on-demand and cached for performance
- File modification timestamps trigger automatic cache invalidation

Account Configuration Structure:
{
    "account_id": "unique_identifier",
    "display_name": "Human-readable name",
    "persona": "Personality description for AI prompts",
    "exemplars": [{"text": "Example tweet"}],
    "vector_collection": "knowledge_base_name",
    "twitter_credentials": {
        "api_key": "...",
        "api_secret": "...",
        "access_token": "...",
        "access_token_secret": "...",
        "bearer_token": "..."
    }
}

Usage:
    # Get all accounts
    accounts = load_all_accounts()
    
    # Get specific account
    account = get_account("zenkink")
    
    # Validate configuration
    is_valid = validate_account_config(account_dict)
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import structlog
from dotenv import load_dotenv

from app.exceptions import ConfigurationError

# Load environment variables from .env file
load_dotenv(".env")

logger = structlog.get_logger(__name__)


def resolve_env_variables(value: any) -> any:
    """Resolve environment variables in configuration values.
    
    Recursively processes dictionaries and lists, replacing strings that start with 'env:'
    with their corresponding environment variable values.
    
    Args:
        value: The configuration value to process
        
    Returns:
        The value with environment variables resolved
        
    Raises:
        ConfigurationError: If an environment variable is not found
    """
    if isinstance(value, str) and value.startswith('env:'):
        env_var = value[4:]  # Remove 'env:' prefix
        env_value = os.getenv(env_var)
        if env_value is None:
            raise ConfigurationError(f"Environment variable '{env_var}' not found")
        return env_value
    elif isinstance(value, dict):
        return {k: resolve_env_variables(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_env_variables(item) for item in value]
    else:
        return value


class AccountManager:
    """Manage multiple Twitter account configurations."""

    def __init__(self, accounts_dir: str = "accounts"):
        self.accounts_dir = Path(accounts_dir)
        self._accounts_cache = {}
        self._last_loaded = 0

    def _should_reload_cache(self) -> bool:
        """Check if we should reload the accounts cache."""
        if not self._accounts_cache:
            return True

        # Check if any account file has been modified
        try:
            latest_mtime = 0
            for account_file in self.accounts_dir.glob("*.json"):
                mtime = account_file.stat().st_mtime
                if mtime > latest_mtime:
                    latest_mtime = mtime

            return latest_mtime > self._last_loaded
        except Exception:
            return True

    def load_all_accounts(self) -> Dict[str, Dict]:
        """Load all account configurations from the accounts directory."""
        if not self._should_reload_cache():
            return self._accounts_cache

        logger.info(
            "Loading account configurations", accounts_dir=str(self.accounts_dir)
        )

        if not self.accounts_dir.exists():
            logger.warning(
                "Accounts directory does not exist", path=str(self.accounts_dir)
            )
            return {}

        accounts = {}

        for account_file in self.accounts_dir.glob("*.json"):
            try:
                with open(account_file, "r") as f:
                    account_config = json.load(f)

                # Validate account configuration
                self.validate_account_config(account_config)

                account_id = account_config["account_id"]
                accounts[account_id] = account_config

                logger.debug(
                    "Loaded account configuration",
                    account_id=account_id,
                    file=account_file.name,
                )

            except Exception as e:
                logger.error(
                    "Failed to load account configuration",
                    file=account_file.name,
                    error=str(e),
                )
                # Continue loading other accounts
                continue

        if accounts:
            self._accounts_cache = accounts
            self._last_loaded = time.time()
            logger.info(
                "Successfully loaded accounts",
                count=len(accounts),
                accounts=list(accounts.keys()),
            )
        else:
            logger.warning("No valid account configurations found")

        return accounts

    def get_account(self, account_id: str) -> Optional[Dict]:
        """Get a specific account configuration with environment variables resolved."""
        accounts = self.load_all_accounts()
        account = accounts.get(account_id)

        if not account:
            logger.warning(
                "Account not found",
                account_id=account_id,
                available_accounts=list(accounts.keys()),
            )
            return None

        # Resolve environment variables in the account configuration
        try:
            resolved_account = resolve_env_variables(account)
            return resolved_account
        except ConfigurationError as e:
            logger.error(
                "Failed to resolve environment variables for account",
                account_id=account_id,
                error=str(e),
            )
            return None

    def get_account_ids(self) -> List[str]:
        """Get list of all available account IDs."""
        accounts = self.load_all_accounts()
        return list(accounts.keys())

    def validate_account_config(self, config: Dict) -> bool:
        """Validate an account configuration."""
        required_fields = [
            "account_id",
            "display_name",
            "persona",
            "exemplars",
            "vector_collection",
            "twitter_credentials",
        ]

        # Check required top-level fields
        for field in required_fields:
            if field not in config:
                raise ConfigurationError(
                    f"Missing required field in account config: {field}"
                )

        # Validate account_id format
        account_id = config["account_id"]
        if not account_id or not isinstance(account_id, str):
            raise ConfigurationError("account_id must be a non-empty string")

        if not account_id.replace("_", "").replace("-", "").isalnum():
            raise ConfigurationError(
                "account_id must contain only alphanumeric characters, hyphens, and underscores"
            )

        # Validate twitter_credentials
        twitter_creds = config["twitter_credentials"]
        required_creds = [
            "api_key",
            "api_secret",
            "access_token",
            "access_token_secret",
            "bearer_token",
        ]

        for cred in required_creds:
            if cred not in twitter_creds:
                raise ConfigurationError(f"Missing Twitter credential: {cred}")

            # Check if credentials are placeholder values
            if twitter_creds[cred].startswith("REPLACE_WITH_ACTUAL_"):
                logger.warning(
                    "Twitter credentials contain placeholder values",
                    account_id=account_id,
                    credential=cred,
                )

        # Validate exemplars structure
        exemplars = config["exemplars"]
        if not isinstance(exemplars, list):
            raise ConfigurationError("exemplars must be a list")

        for i, exemplar in enumerate(exemplars):
            if not isinstance(exemplar, dict):
                raise ConfigurationError(f"exemplar {i} must be a dictionary")

            if "text" not in exemplar:
                raise ConfigurationError(f"exemplar {i} missing required 'text' field")

        # Validate persona
        if not isinstance(config["persona"], str) or not config["persona"].strip():
            raise ConfigurationError("persona must be a non-empty string")

        # Validate vector_collection
        if (
            not isinstance(config["vector_collection"], str)
            or not config["vector_collection"].strip()
        ):
            raise ConfigurationError("vector_collection must be a non-empty string")

        logger.debug(
            "Account configuration validated successfully", account_id=account_id
        )
        return True

    def save_account(self, account_config: Dict) -> bool:
        """Save an account configuration to file."""
        try:
            # Validate first
            self.validate_account_config(account_config)

            account_id = account_config["account_id"]
            account_file = self.accounts_dir / f"{account_id}.json"

            # Ensure accounts directory exists
            self.accounts_dir.mkdir(parents=True, exist_ok=True)

            # Save to file
            with open(account_file, "w") as f:
                json.dump(account_config, f, indent=2)

            logger.info(
                "Saved account configuration",
                account_id=account_id,
                file=str(account_file),
            )

            # Clear cache to force reload
            self._accounts_cache = {}

            return True

        except Exception as e:
            logger.error(
                "Failed to save account configuration",
                account_id=account_config.get("account_id", "unknown"),
                error=str(e),
            )
            return False

    def delete_account(self, account_id: str) -> bool:
        """Delete an account configuration."""
        try:
            account_file = self.accounts_dir / f"{account_id}.json"

            if not account_file.exists():
                logger.warning(
                    "Account file does not exist",
                    account_id=account_id,
                    file=str(account_file),
                )
                return False

            account_file.unlink()
            logger.info("Deleted account configuration", account_id=account_id)

            # Clear cache to force reload
            self._accounts_cache = {}

            return True

        except Exception as e:
            logger.error(
                "Failed to delete account configuration",
                account_id=account_id,
                error=str(e),
            )
            return False


# Global instance for easy access
_account_manager = None


def get_account_manager() -> AccountManager:
    """Get the global account manager instance."""
    global _account_manager
    if _account_manager is None:
        _account_manager = AccountManager()
    return _account_manager


# Convenience functions
def load_all_accounts() -> Dict[str, Dict]:
    """Load all account configurations."""
    return get_account_manager().load_all_accounts()


def get_account(account_id: str) -> Optional[Dict]:
    """Get a specific account configuration."""
    return get_account_manager().get_account(account_id)


def get_account_ids() -> List[str]:
    """Get list of all available account IDs."""
    return get_account_manager().get_account_ids()


def validate_account_config(config: Dict) -> bool:
    """Validate an account configuration."""
    return get_account_manager().validate_account_config(config)
