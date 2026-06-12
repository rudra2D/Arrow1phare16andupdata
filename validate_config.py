#!/usr/bin/env python3
"""
Arrow Project - Configuration System Validation & Demonstration

This script demonstrates the secure configuration system in action and
validates that all components are working correctly. Run this to verify
your setup before deploying.

Usage:
    python validate_config.py
"""

import os
import sys
from pathlib import Path


def print_header(title: str) -> None:
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_status(message: str, status: str = "INFO") -> None:
    """Print a status message."""
    icons = {
        "INFO": "ℹ️ ",
        "SUCCESS": "✅",
        "WARNING": "⚠️ ",
        "ERROR": "❌",
    }
    icon = icons.get(status, "•")
    print(f"{icon} {message}")


def check_file_exists(path: str) -> bool:
    """Check if a file exists."""
    exists = Path(path).exists()
    if exists:
        print_status(f"File found: {path}", "SUCCESS")
    else:
        print_status(f"File missing: {path}", "ERROR")
    return exists


def check_env_file() -> bool:
    """Check if .env file exists and is readable."""
    print_header("1. Environment File Check")
    
    env_path = Path(".env")
    if not env_path.exists():
        print_status(".env file not found", "WARNING")
        print_status("Run: cp .env.example .env", "INFO")
        return False
    
    try:
        with open(env_path, 'r') as f:
            content = f.read()
            lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('#')]
            print_status(f".env file found with {len(lines)} configuration lines", "SUCCESS")
            return True
    except PermissionError:
        print_status(".env file exists but cannot be read (permission denied)", "ERROR")
        return False


def check_config_loader() -> bool:
    """Check if config_loader module exists."""
    print_header("2. Configuration Loader Module Check")
    
    loader_path = Path("modules/config_loader.py")
    if not loader_path.exists():
        print_status("config_loader.py not found", "ERROR")
        return False
    
    print_status("config_loader.py found", "SUCCESS")
    
    # Try to import
    try:
        from modules.config_loader import (
            initialize_configuration,
            get_configuration,
            MissingCredentialError,
        )
        print_status("Module imports successful", "SUCCESS")
        return True
    except ImportError as e:
        print_status(f"Failed to import module: {e}", "ERROR")
        return False


def check_gitignore() -> bool:
    """Check if .gitignore protects .env."""
    print_header("3. Git Security Check")
    
    gitignore_path = Path(".gitignore")
    if not gitignore_path.exists():
        print_status(".gitignore file not found", "WARNING")
        return False
    
    try:
        with open(gitignore_path, 'r') as f:
            content = f.read()
            if ".env" in content:
                print_status(".env is protected in .gitignore", "SUCCESS")
                return True
            else:
                print_status(".env is NOT in .gitignore (SECURITY RISK!)", "ERROR")
                return False
    except Exception as e:
        print_status(f"Error reading .gitignore: {e}", "ERROR")
        return False


def check_required_credentials() -> dict:
    """Check if required credentials are configured."""
    print_header("4. Required Credentials Check")
    
    try:
        from modules.config_loader import get_configuration
        
        config = get_configuration()
        
        checks = {
            "GEMINI_API_KEY": bool(config.gemini_api_key),
            "BOT_TOKEN": bool(config.bot_token),
        }
        
        all_present = True
        for key, present in checks.items():
            if present:
                print_status(f"{key}: Configured ✓", "SUCCESS")
            else:
                print_status(f"{key}: Missing! (REQUIRED)", "ERROR")
                all_present = False
        
        return {"status": all_present, "details": checks}
        
    except Exception as e:
        print_status(f"Error checking credentials: {e}", "ERROR")
        return {"status": False, "details": {}}


def check_optional_settings() -> dict:
    """Check optional configuration settings."""
    print_header("5. Optional Settings Check")
    
    try:
        from modules.config_loader import get_configuration
        
        config = get_configuration()
        
        optional_checks = {
            "TELEGRAM_USER_ID": config.telegram_user_id,
            "VOICE_RECORD_SECONDS": config.voice_record_seconds,
            "VOICE_LANGUAGE": config.voice_language,
            "GEMINI_MODEL": config.gemini_model,
        }
        
        for key, value in optional_checks.items():
            status = "Configured" if value else "Not set"
            symbol = "✓" if value else "○"
            print_status(f"{key}: {status} ({value}) {symbol}", "INFO")
        
        return {"status": True, "details": optional_checks}
        
    except Exception as e:
        print_status(f"Error checking settings: {e}", "ERROR")
        return {"status": False, "details": {}}


def demonstrate_usage() -> None:
    """Demonstrate how to use the configuration system."""
    print_header("6. Usage Examples")
    
    print("\n--- Example 1: Load Configuration ---")
    print("""
from modules.config_loader import get_configuration

config = get_configuration()
print(f"Using model: {config.gemini_model}")
print(f"Voice duration: {config.voice_record_seconds} seconds")
    """)
    
    print("\n--- Example 2: Convenience Getters ---")
    print("""
from modules.config_loader import get_gemini_api_key, get_bot_token

api_key = get_gemini_api_key()  # Returns string or raises error
token = get_bot_token()          # Returns string or raises error
    """)
    
    print("\n--- Example 3: Error Handling ---")
    print("""
from modules.config_loader import get_configuration, MissingCredentialError

try:
    config = get_configuration()
except MissingCredentialError as e:
    print(f"Setup required: {e}")
    """)


def print_security_summary() -> None:
    """Print security best practices summary."""
    print_header("7. Security Best Practices Summary")
    
    practices = [
        ("DO", "Keep .env in .gitignore", "✓"),
        ("DO", "Use get_configuration() for all access", "✓"),
        ("DO", "Set env vars in production", "✓"),
        ("DO", "Rotate keys regularly", "✓"),
        ("DO", "Back up .env securely", "✓"),
        ("DON'T", "Commit .env to git", "✗"),
        ("DON'T", "Print API keys in logs", "✗"),
        ("DON'T", "Hardcode credentials", "✗"),
        ("DON'T", "Share .env via email", "✗"),
    ]
    
    for action, practice, result in practices:
        prefix = "✅" if action == "DO" else "❌"
        print(f"{prefix} {action:6} {practice:35} {result}")


def main() -> int:
    """Run all validation checks."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 10 + "Arrow Project - Configuration Validation" + " " * 17 + "║")
    print("╚" + "=" * 68 + "╝")
    
    results = []
    
    # Run checks
    results.append(("Files Present", check_file_exists(".env.example")))
    results.append((".env File", check_env_file()))
    results.append(("Config Loader", check_config_loader()))
    results.append((".gitignore", check_gitignore()))
    
    # Check credentials (might fail if not configured)
    try:
        creds = check_required_credentials()
        results.append(("Credentials", creds["status"]))
        check_optional_settings()
    except Exception as e:
        print_status(f"Could not verify credentials: {e}", "WARNING")
        results.append(("Credentials", False))
    
    # Show usage examples
    demonstrate_usage()
    print_security_summary()
    
    # Final summary
    print_header("VALIDATION SUMMARY")
    
    passed = sum(1 for _, status in results if status)
    total = len(results)
    
    for check_name, status in results:
        symbol = "✅" if status else "❌"
        print(f"{symbol} {check_name:20} {'PASS' if status else 'FAIL'}")
    
    print(f"\nResult: {passed}/{total} checks passed")
    
    if passed == total:
        print_status("✅ All validation checks passed! System ready.", "SUCCESS")
        print_status("Next: Fill in your credentials in .env and test with real keys", "INFO")
        return 0
    else:
        print_status("⚠️ Some checks failed. See above for details.", "WARNING")
        print_status("Common issues: Missing .env file, incomplete credentials", "INFO")
        return 1


if __name__ == "__main__":
    sys.exit(main())
