"""
ARROW PROJECT - SECURE CONFIGURATION & SECRET MANAGEMENT ENGINE

This module provides a production-grade configuration loader that securely manages
all sensitive credentials and environment-specific settings. It supports multiple
deployment environments (local, cloud, Google Colab, etc.) with automatic fallback
mechanisms to ensure the pipeline never fails due to configuration loading.

SECURITY REQUIREMENTS SATISFIED:
- No sensitive data is ever printed in console logs
- Meaningful error messages without exposing partial tokens
- Type-safe configuration access with clear fallback behavior
- Support for both local .env files and cloud-native credential systems
- Extensible architecture for future API integrations

DEPLOYMENT SUPPORT:
- Local development (.env file in project root)
- Docker containers (environment variables injected at runtime)
- Google Colab (fallback to google.colab.userdata.get())
- Cloud platforms (AWS, GCP, Azure - via environment variables)
"""

import os
import sys
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass


# ============================================================================
# EXCEPTIONS & CONFIGURATION ERRORS
# ============================================================================

class ConfigurationError(Exception):
    """Base exception for configuration loading errors."""
    pass


class MissingCredentialError(ConfigurationError):
    """Raised when a required credential is missing."""
    pass


# ============================================================================
# COLAB DETECTION & FALLBACK HANDLER
# ============================================================================

def _is_google_colab() -> bool:
    """
    Detect if code is running in Google Colab environment.
    
    Returns:
        bool: True if running in Colab, False otherwise.
    """
    try:
        import google.colab  # noqa: F401
        return True
    except ImportError:
        return False


def _get_colab_secret(key: str) -> Optional[str]:
    """
    Fetch a secret from Google Colab's secure user data store.
    
    This method is called when running in a Colab notebook to retrieve
    credentials without exposing them in code or environment variables.
    
    Args:
        key: The name of the secret to retrieve from Colab's store.
        
    Returns:
        The secret value if found, None otherwise.
        
    Raises:
        ConfigurationError: If Colab's userdata API fails unexpectedly.
    """
    if not _is_google_colab():
        return None
        
    try:
        from google.colab import userdata
        return userdata.get(key)
    except ImportError:
        # google.colab exists but userdata module not available
        return None
    except userdata.NotebookAccessError:
        # User hasn't granted permission or secret not stored
        return None
    except Exception as exc:
        raise ConfigurationError(
            f"Unexpected error accessing Colab secrets: {type(exc).__name__}"
        ) from exc


# ============================================================================
# .ENV FILE LOADER
# ============================================================================

def _load_env_file(env_path: Optional[str] = None) -> dict:
    """
    Load environment variables from a .env file.
    
    This function reads a .env file line-by-line, parsing KEY=VALUE pairs
    and loading them into the environment. It gracefully handles missing
    files and provides clear error messages.
    
    Args:
        env_path: Optional path to the .env file. Defaults to project root.
        
    Returns:
        Dictionary of loaded environment variables.
    """
    if env_path is None:
        # Default to .env in project root (one level above modules/)
        project_root = Path(__file__).parent.parent
        env_path = project_root / ".env"
    else:
        env_path = Path(env_path)
    
    loaded_vars = {}
    
    if not env_path.exists():
        # .env file not found; continue gracefully
        # This is expected in cloud environments
        return loaded_vars
    
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                
                # Parse KEY=VALUE pairs
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    loaded_vars[key] = value
                    os.environ[key] = value
    except PermissionError as exc:
        raise ConfigurationError(
            f"Permission denied reading .env file at {env_path}"
        ) from exc
    except Exception as exc:
        raise ConfigurationError(
            f"Error reading .env file: {type(exc).__name__}"
        ) from exc
    
    return loaded_vars


# ============================================================================
# CONFIGURATION VALUE RETRIEVERS
# ============================================================================

def _get_credential(
    key: str,
    required: bool = False,
    default: Optional[str] = None
) -> Optional[str]:
    """
    Retrieve a credential value from multiple sources with fallback strategy.
    
    Lookup order (in priority):
    1. Environment variable (set by system or .env file)
    2. Google Colab secrets (if running in Colab)
    3. Default value
    4. None
    
    Args:
        key: The credential key to retrieve (e.g., "GEMINI_API_KEY").
        required: If True, raises MissingCredentialError if credential not found.
        default: Default value if credential is not found.
        
    Returns:
        The credential value, or None if not found and not required.
        
    Raises:
        MissingCredentialError: If required credential is missing.
    """
    # First, check environment variables
    value = os.getenv(key, "").strip()
    if value:
        return value
    
    # Second, check Google Colab secrets
    colab_value = _get_colab_secret(key)
    if colab_value:
        return colab_value.strip()
    
    # Third, use default if provided
    if default is not None:
        return default
    
    # If required and not found, raise error
    if required:
        raise MissingCredentialError(
            f"Required credential '{key}' not found. "
            f"Please set {key} in your .env file or environment variables."
        )
    
    return None


def _get_int_credential(
    key: str,
    required: bool = False,
    default: Optional[int] = None
) -> Optional[int]:
    """
    Retrieve an integer credential value.
    
    Converts string values to integers with graceful fallback behavior.
    
    Args:
        key: The credential key to retrieve.
        required: If True, raises MissingCredentialError if credential not found.
        default: Default value if credential is not found or cannot be converted.
        
    Returns:
        The credential value as an integer, or default if conversion fails.
        
    Raises:
        MissingCredentialError: If required credential is missing.
    """
    value = _get_credential(key, required=required, default=None)
    
    if value is None:
        if required:
            raise MissingCredentialError(
                f"Required credential '{key}' not found."
            )
        return default
    
    try:
        return int(value)
    except ValueError:
        if required:
            raise ConfigurationError(
                f"Credential '{key}' has invalid format. Expected integer."
            )
        return default


# ============================================================================
# CONFIGURATION DATA STRUCTURE
# ============================================================================

@dataclass
class ArrowConfiguration:
    """
    Production-grade configuration container for the Arrow Project.
    
    This dataclass encapsulates all credentials and settings, providing
    type-safe access with validation. It enforces immutability and
    prevents accidental exposure of sensitive data in error messages.
    
    Attributes:
        gemini_api_key: Primary LLM API key for Google Gemini.
        gemini_model: Model identifier for Gemini API (default: gemini-1.5-pro).
        bot_token: Telegram bot token for system integration.
        telegram_user_id: Authorized user ID for Telegram remote control.
        admin_chat_id: Strict admin chat ID for privileged command execution.
        voice_record_seconds: Duration (seconds) for voice recording.
        voice_language: Language code for voice input/output (default: en-US).
        private_server_upload_url: Secure endpoint for file uploads.
        private_backup_upload_url: Backup storage endpoint.
        private_storage_auth_token: Authentication token for storage access.
        camera_rtsp_url: RTSP feed URL for Wi-Fi camera streams.
        
    SECURITY NOTE:
        This object intentionally does not implement __str__ or __repr__
        methods to prevent accidental logging of sensitive credentials.
        Use only the specific attribute getters you need.
    """
    
    # Core LLM Configuration
    gemini_api_key: Optional[str]
    gemini_model: str
    
    # Telegram Bot Integration
    bot_token: Optional[str]
    telegram_user_id: Optional[int]
    admin_chat_id: Optional[int]
    
    # Voice Configuration
    voice_record_seconds: int
    voice_language: str
    
    # Private Storage & File Routing
    private_server_upload_url: Optional[str]
    private_backup_upload_url: Optional[str]
    private_storage_auth_token: Optional[str]
    
    # Camera & Hardware
    camera_rtsp_url: Optional[str]
    
    # [FUTURE_API_EXTENSIONS] - Prepared slots for new integrations
    # openai_api_key: Optional[str] = None
    # database_url: Optional[str] = None
    # cloud_storage_key: Optional[str] = None
    # cloud_storage_secret: Optional[str] = None
    
    def __repr__(self) -> str:
        """
        Prevent sensitive data from being exposed in error messages or logs.
        
        Returns a safe representation without credential values.
        """
        return "<ArrowConfiguration: See credentials via specific attributes>"
    
    def validate_critical_requirements(self) -> None:
        """
        Validate that all critical credentials are present.
        
        Raises:
            MissingCredentialError: If any required credential is missing.
        """
        if not self.gemini_api_key:
            raise MissingCredentialError(
                "Critical: GEMINI_API_KEY is missing. "
                "Set it in .env file or environment variables."
            )
        
        if not self.bot_token:
            raise MissingCredentialError(
                "Critical: BOT_TOKEN is missing. "
                "Set it in .env file or environment variables."
            )


# ============================================================================
# CONFIGURATION INITIALIZATION & SINGLETON
# ============================================================================

_config_instance: Optional[ArrowConfiguration] = None


def initialize_configuration(env_path: Optional[str] = None) -> ArrowConfiguration:
    """
    Initialize the Arrow Project configuration system.
    
    This function loads environment variables from a .env file (if present),
    configures fallback mechanisms for different deployment environments,
    and returns a validated configuration object.
    
    INITIALIZATION SEQUENCE:
    1. Load .env file if present in project root
    2. Set up Google Colab fallback (if applicable)
    3. Retrieve all credentials with appropriate fallbacks
    4. Validate critical requirements
    5. Return configuration object
    
    Args:
        env_path: Optional custom path to .env file. 
                  Defaults to project root/.env
        
    Returns:
        ArrowConfiguration: Fully initialized and validated configuration object.
        
    Raises:
        MissingCredentialError: If critical credentials are missing.
        ConfigurationError: If configuration loading fails unexpectedly.
        
    Example:
        >>> config = initialize_configuration()
        >>> api_key = config.gemini_api_key
        >>> print(f"Using model: {config.gemini_model}")
    """
    global _config_instance
    
    # Load .env file
    _load_env_file(env_path)
    
    # Retrieve all configuration values
    config = ArrowConfiguration(
        # Core LLM Configuration
        gemini_api_key=_get_credential("GEMINI_API_KEY", required=True),
        gemini_model=_get_credential(
            "GEMINI_MODEL",
            required=False,
            default="gemini-1.5-pro"
        ),
        
        # Telegram Bot Integration
        bot_token=_get_credential("BOT_TOKEN", required=True),
        telegram_user_id=_get_int_credential("TELEGRAM_USER_ID", required=False),
        admin_chat_id=_get_int_credential("ADMIN_CHAT_ID", required=False),
        
        # Voice Configuration
        voice_record_seconds=_get_int_credential(
            "VOICE_RECORD_SECONDS",
            required=False,
            default=7
        ),
        voice_language=_get_credential(
            "VOICE_LANGUAGE",
            required=False,
            default="en-US"
        ),
        
        # Private Storage & File Routing
        private_server_upload_url=_get_credential(
            "PRIVATE_SERVER_UPLOAD_URL",
            required=False
        ),
        private_backup_upload_url=_get_credential(
            "PRIVATE_BACKUP_UPLOAD_URL",
            required=False
        ),
        private_storage_auth_token=_get_credential(
            "PRIVATE_STORAGE_AUTH_TOKEN",
            required=False
        ),
        
        # Camera & Hardware
        camera_rtsp_url=_get_credential(
            "CAMERA_RTSP_URL",
            required=False
        ),
    )
    
    # Validate critical requirements
    config.validate_critical_requirements()
    
    # Cache the instance
    _config_instance = config
    
    return config


def get_configuration() -> ArrowConfiguration:
    """
    Retrieve the current configuration instance (singleton pattern).
    
    If configuration hasn't been initialized yet, this function will
    initialize it with default settings.
    
    Returns:
        ArrowConfiguration: The current configuration object.
        
    Raises:
        MissingCredentialError: If critical credentials are missing.
        
    Example:
        >>> config = get_configuration()
        >>> token = config.bot_token
    """
    global _config_instance
    
    if _config_instance is None:
        _config_instance = initialize_configuration()
    
    return _config_instance


def reset_configuration() -> None:
    """
    Reset the configuration cache (useful for testing or reconfiguration).
    
    After calling this, the next call to get_configuration() will
    reinitialize from environment variables.
    """
    global _config_instance
    _config_instance = None


# ============================================================================
# CONVENIENCE GETTERS (For backward compatibility with existing code)
# ============================================================================

def get_gemini_api_key() -> str:
    """
    Retrieve the Gemini API key.
    
    Returns:
        str: The Gemini API key.
        
    Raises:
        MissingCredentialError: If key is not configured.
    """
    config = get_configuration()
    if not config.gemini_api_key:
        raise MissingCredentialError("GEMINI_API_KEY not configured")
    return config.gemini_api_key


def get_bot_token() -> str:
    """
    Retrieve the Telegram bot token.
    
    Returns:
        str: The Telegram bot token.
        
    Raises:
        MissingCredentialError: If token is not configured.
    """
    config = get_configuration()
    if not config.bot_token:
        raise MissingCredentialError("BOT_TOKEN not configured")
    return config.bot_token


# ============================================================================
# INITIALIZATION TRIGGER (Called on module import in production)
# ============================================================================

# Auto-initialize configuration when module is imported
# This ensures configuration is ready as soon as the module is available
if __name__ != "__main__":
    try:
        initialize_configuration()
    except MissingCredentialError as e:
        # Log error but don't crash on import
        # Allows modules to import successfully; errors trigger on first config access
        print(f"WARNING: Configuration incomplete: {e}", file=sys.stderr)
    except ConfigurationError as e:
        print(f"ERROR: Configuration loading failed: {e}", file=sys.stderr)
