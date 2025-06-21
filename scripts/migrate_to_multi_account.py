#!/usr/bin/env python3
"""
Migration script - Convert single-account to multi-account system.

This utility helps users migrate from the original single-account bot setup
to the new multi-account architecture. It automates the conversion process
while preserving existing configurations and credentials.

Migration Process:
1. Load Twitter credentials from environment variables
2. Create/update zenkink.json account configuration
3. Validate the migrated configuration
4. Test Twitter API connection
5. Provide next steps for adding more accounts

Key Features:
- Preserves existing credentials and settings
- Validates configuration before saving
- Tests Twitter connection after migration
- Provides clear instructions for multi-account setup
- Backward compatible with existing deployments

Usage:
    python scripts/migrate_to_multi_account.py

The script is idempotent - running it multiple times is safe and will
verify the existing migration status.
"""

import json
import os
import sys
from pathlib import Path

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.account_manager import validate_account_config, get_account
from app.deps import get_twitter_client
from dotenv import load_dotenv


def load_environment():
    """Load environment variables."""
    # Try to load from config/.env
    env_path = Path("config/.env")
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✓ Loaded environment from {env_path}")
    else:
        print(f"⚠ No config/.env file found at {env_path}")
    
    return {
        "TWITTER_API_KEY": os.getenv("TWITTER_API_KEY"),
        "TWITTER_API_SECRET": os.getenv("TWITTER_API_SECRET"),
        "TWITTER_ACCESS_TOKEN": os.getenv("TWITTER_ACCESS_TOKEN"),
        "TWITTER_ACCESS_TOKEN_SECRET": os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
        "TWITTER_BEARER_TOKEN": os.getenv("TWITTER_BEARER_TOKEN")
    }


def check_existing_account():
    """Check if startupquotes account already exists and is valid."""
    try:
        account = get_account("startupquotes")
        if account:
            print("✓ startupquotes account configuration already exists")
            validate_account_config(account)
            print("✓ Account configuration is valid")
            return True
        return False
    except Exception as e:
        print(f"⚠ Existing account configuration has issues: {e}")
        return False


def update_account_credentials():
    """Update the startupquotes.json file with actual Twitter credentials from environment."""
    try:
        # Load current environment
        env_vars = load_environment()
        
        # Check for missing credentials
        missing_creds = [key for key, value in env_vars.items() if not value]
        if missing_creds:
            print(f"⚠ Missing environment variables: {', '.join(missing_creds)}")
            print("Please set these in your config/.env file before running the migration.")
            return False
        
        # Load existing account config
        account_file = Path("accounts/startupquotes.json")
        if not account_file.exists():
            print(f"❌ Account file not found: {account_file}")
            return False
        
        with open(account_file, 'r') as f:
            account_config = json.load(f)
        
        # Update credentials
        account_config["twitter_credentials"] = {
            "api_key": env_vars["TWITTER_API_KEY"],
            "api_secret": env_vars["TWITTER_API_SECRET"],
            "access_token": env_vars["TWITTER_ACCESS_TOKEN"],
            "access_token_secret": env_vars["TWITTER_ACCESS_TOKEN_SECRET"],
            "bearer_token": env_vars["TWITTER_BEARER_TOKEN"]
        }
        
        # Validate the updated configuration
        validate_account_config(account_config)
        
        # Save the updated configuration
        with open(account_file, 'w') as f:
            json.dump(account_config, f, indent=2)
        
        print(f"✓ Updated {account_file} with Twitter credentials from environment")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update account credentials: {e}")
        return False


def test_account_connection():
    """Test Twitter connection for the startupquotes account."""
    try:
        print("Testing Twitter connection for startupquotes account...")
        
        # Test the connection
        client = get_twitter_client(account_id="startupquotes")
        user = client.get_me()
        
        if user.data:
            print(f"✓ Successfully connected to Twitter as @{user.data.username}")
            print(f"  User ID: {user.data.id}")
            print(f"  Display Name: {user.data.name}")
            return True
        else:
            print("❌ Twitter connection test failed - no user data returned")
            return False
            
    except Exception as e:
        print(f"❌ Twitter connection test failed: {e}")
        return False


def show_next_steps():
    """Show user what to do next."""
    print("\n" + "="*50)
    print("MIGRATION COMPLETE! 🎉")
    print("="*50)
    print("\nNext steps:")
    print("1. The startupquotes account is now configured and ready to use")
    print("2. The system will automatically use account-specific settings")
    print("3. The scheduler will post tweets for all configured accounts")
    print("\nTo add more accounts:")
    print("1. Create a new JSON file in accounts/ (e.g., accounts/mybot.json)")
    print("2. Copy the structure from accounts/startupquotes.json")
    print("3. Update the account_id, display_name, persona, exemplars, and credentials")
    print("4. Set the vector_collection name (can be shared or unique)")
    print("\nTo test the setup:")
    print("1. Start the application: uvicorn app.main:app --host 0.0.0.0 --port 8582")
    print("2. Visit http://localhost:8582")
    print("3. Use the new account-specific endpoints:")
    print("   - GET /api/accounts - list all accounts")
    print("   - GET /api/status/startupquotes - get account status")
    print("   - POST /api/force-post/startupquotes - force post for account")
    print("\nThe system maintains backward compatibility with the old API endpoints.")


def main():
    """Main migration function."""
    print("Multi-Account Migration Script")
    print("=" * 30)
    
    # Change to project root directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    print(f"Working directory: {project_root}")
    
    # Check if we're already migrated
    if check_existing_account():
        test_result = test_account_connection()
        if test_result:
            print("\n✓ Migration already complete and working!")
            show_next_steps()
            return True
        else:
            print("\n⚠ Account exists but Twitter connection failed.")
            print("The credentials in accounts/startupquotes.json may need to be updated.")
    
    print("\nStarting migration...")
    
    # Step 1: Update credentials
    if not update_account_credentials():
        print("\n❌ Migration failed at credential update step")
        return False
    
    # Step 2: Test connection
    if not test_account_connection():
        print("\n❌ Migration failed at connection test step")
        print("Please check your Twitter credentials and try again")
        return False
    
    # Step 3: Success!
    show_next_steps()
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nMigration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error during migration: {e}")
        sys.exit(1)