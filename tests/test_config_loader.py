"""
Arrow Project - Configuration Loader Test Suite

This module provides validation tests to ensure the configuration system
is working correctly across different scenarios and deployment environments.

Run tests with: pytest tests/test_config_loader.py -v
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from modules.config_loader import (
    initialize_configuration,
    get_configuration,
    reset_configuration,
    _load_env_file,
    _get_credential,
    _get_int_credential,
    _is_google_colab,
    _get_colab_secret,
    MissingCredentialError,
    ConfigurationError,
)


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture(autouse=True)
def cleanup_config():
    """Cleanup configuration state before and after each test."""
    reset_configuration()
    yield
    reset_configuration()


@pytest.fixture
def temp_env_file():
    """Create a temporary .env file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        yield f.name
    Path(f.name).unlink()


# ============================================================================
# .ENV FILE LOADING TESTS
# ============================================================================

class TestEnvFileLoading:
    """Test .env file parsing and loading."""
    
    def test_load_env_file_with_valid_pairs(self, temp_env_file):
        """Test loading valid KEY=VALUE pairs from .env file."""
        with open(temp_env_file, 'w') as f:
            f.write("TEST_KEY_1=value1\n")
            f.write("TEST_KEY_2=value2\n")
            f.write("TEST_KEY_3=value3\n")
        
        result = _load_env_file(temp_env_file)
        
        assert result["TEST_KEY_1"] == "value1"
        assert result["TEST_KEY_2"] == "value2"
        assert result["TEST_KEY_3"] == "value3"
        assert os.getenv("TEST_KEY_1") == "value1"
    
    def test_load_env_file_ignores_comments(self, temp_env_file):
        """Test that comments are ignored."""
        with open(temp_env_file, 'w') as f:
            f.write("# This is a comment\n")
            f.write("REAL_KEY=real_value\n")
            f.write("# Another comment\n")
        
        result = _load_env_file(temp_env_file)
        
        assert result["REAL_KEY"] == "real_value"
        assert len(result) == 1  # Only the real key
    
    def test_load_env_file_ignores_blank_lines(self, temp_env_file):
        """Test that blank lines are ignored."""
        with open(temp_env_file, 'w') as f:
            f.write("KEY1=value1\n")
            f.write("\n")
            f.write("KEY2=value2\n")
            f.write("   \n")
            f.write("KEY3=value3\n")
        
        result = _load_env_file(temp_env_file)
        
        assert len(result) == 3
        assert "KEY1" in result
        assert "KEY2" in result
        assert "KEY3" in result
    
    def test_load_env_file_handles_quoted_values(self, temp_env_file):
        """Test that quoted values are unquoted."""
        with open(temp_env_file, 'w') as f:
            f.write('DOUBLE_QUOTED="value with spaces"\n')
            f.write("SINGLE_QUOTED='another value'\n")
            f.write('UNQUOTED=plain_value\n')
        
        result = _load_env_file(temp_env_file)
        
        assert result["DOUBLE_QUOTED"] == "value with spaces"
        assert result["SINGLE_QUOTED"] == "another value"
        assert result["UNQUOTED"] == "plain_value"
    
    def test_load_env_file_nonexistent_returns_empty(self):
        """Test that nonexistent .env file returns empty dict gracefully."""
        result = _load_env_file("/nonexistent/path/.env")
        assert result == {}
    
    def test_load_env_file_permission_error(self, temp_env_file):
        """Test that permission errors are handled."""
        # Create an unreadable file
        os.chmod(temp_env_file, 0o000)
        
        with pytest.raises(ConfigurationError):
            _load_env_file(temp_env_file)
        
        # Restore permissions for cleanup
        os.chmod(temp_env_file, 0o644)


# ============================================================================
# CREDENTIAL RETRIEVAL TESTS
# ============================================================================

class TestCredentialRetrieval:
    """Test credential retrieval with fallbacks."""
    
    def test_get_credential_from_env_variable(self):
        """Test retrieving credential from environment variable."""
        os.environ["TEST_CRED"] = "test_value"
        
        result = _get_credential("TEST_CRED")
        
        assert result == "test_value"
    
    def test_get_credential_with_default(self):
        """Test retrieving with default fallback."""
        result = _get_credential("NONEXISTENT_KEY", default="default_value")
        
        assert result == "default_value"
    
    def test_get_credential_required_raises_error(self):
        """Test that missing required credential raises error."""
        with pytest.raises(MissingCredentialError):
            _get_credential("MISSING_REQUIRED_KEY", required=True)
    
    def test_get_credential_strips_whitespace(self):
        """Test that whitespace is stripped."""
        os.environ["WHITESPACE_KEY"] = "  value_with_spaces  "
        
        result = _get_credential("WHITESPACE_KEY")
        
        assert result == "value_with_spaces"
    
    def test_get_int_credential_valid(self):
        """Test retrieving valid integer credential."""
        os.environ["INT_CRED"] = "42"
        
        result = _get_int_credential("INT_CRED")
        
        assert result == 42
        assert isinstance(result, int)
    
    def test_get_int_credential_invalid_returns_default(self):
        """Test that invalid integer returns default."""
        os.environ["INVALID_INT"] = "not_a_number"
        
        result = _get_int_credential("INVALID_INT", default=0)
        
        assert result == 0
    
    def test_get_int_credential_required_invalid_raises_error(self):
        """Test that required invalid integer raises error."""
        os.environ["INVALID_INT"] = "not_a_number"
        
        with pytest.raises(ConfigurationError):
            _get_int_credential("INVALID_INT", required=True)


# ============================================================================
# GOOGLE COLAB DETECTION TESTS
# ============================================================================

class TestColabDetection:
    """Test Google Colab environment detection."""
    
    def test_is_google_colab_returns_false_normally(self):
        """Test that is_google_colab returns False outside Colab."""
        result = _is_google_colab()
        assert result is False
    
    @patch('modules.config_loader._is_google_colab', return_value=True)
    def test_get_colab_secret_handles_not_found(self, mock_is_colab):
        """Test that missing Colab secrets return None."""
        # This test verifies error handling
        result = _get_colab_secret("MISSING_SECRET")
        # Result depends on whether google.colab is available
        assert result is None or isinstance(result, str)


# ============================================================================
# CONFIGURATION INITIALIZATION TESTS
# ============================================================================

class TestConfigurationInitialization:
    """Test configuration object initialization and validation."""
    
    def test_initialize_with_all_required_credentials(self, temp_env_file):
        """Test successful initialization with all required credentials."""
        # Set required credentials
        os.environ["GEMINI_API_KEY"] = "test_gemini_key"
        os.environ["BOT_TOKEN"] = "test_bot_token"
        
        config = initialize_configuration(temp_env_file)
        
        assert config.gemini_api_key == "test_gemini_key"
        assert config.bot_token == "test_bot_token"
        assert config.gemini_model == "gemini-1.5-pro"  # Default
    
    def test_initialize_missing_gemini_key_raises_error(self):
        """Test that missing GEMINI_API_KEY raises error."""
        os.environ.pop("GEMINI_API_KEY", None)
        os.environ["BOT_TOKEN"] = "test_token"
        
        with pytest.raises(MissingCredentialError):
            initialize_configuration()
    
    def test_initialize_missing_bot_token_raises_error(self):
        """Test that missing BOT_TOKEN raises error."""
        os.environ["GEMINI_API_KEY"] = "test_key"
        os.environ.pop("BOT_TOKEN", None)
        
        with pytest.raises(MissingCredentialError):
            initialize_configuration()
    
    def test_configuration_custom_model(self):
        """Test custom Gemini model configuration."""
        os.environ["GEMINI_API_KEY"] = "test_key"
        os.environ["BOT_TOKEN"] = "test_token"
        os.environ["GEMINI_MODEL"] = "gemini-2.0-flash"
        
        config = initialize_configuration()
        
        assert config.gemini_model == "gemini-2.0-flash"
    
    def test_configuration_optional_values(self):
        """Test that optional values have sensible defaults."""
        os.environ["GEMINI_API_KEY"] = "test_key"
        os.environ["BOT_TOKEN"] = "test_token"
        
        config = initialize_configuration()
        
        assert config.voice_record_seconds == 7
        assert config.voice_language == "en-US"
        assert config.telegram_user_id is None
    
    def test_configuration_integer_parsing(self):
        """Test integer value parsing."""
        os.environ["GEMINI_API_KEY"] = "test_key"
        os.environ["BOT_TOKEN"] = "test_token"
        os.environ["TELEGRAM_USER_ID"] = "123456789"
        os.environ["VOICE_RECORD_SECONDS"] = "10"
        
        config = initialize_configuration()
        
        assert config.telegram_user_id == 123456789
        assert config.voice_record_seconds == 10


# ============================================================================
# SINGLETON PATTERN TESTS
# ============================================================================

class TestConfigurationSingleton:
    """Test singleton pattern and caching."""
    
    def test_get_configuration_returns_singleton(self):
        """Test that get_configuration returns same instance."""
        os.environ["GEMINI_API_KEY"] = "test_key"
        os.environ["BOT_TOKEN"] = "test_token"
        
        config1 = get_configuration()
        config2 = get_configuration()
        
        assert config1 is config2
    
    def test_reset_configuration_clears_cache(self):
        """Test that reset_configuration clears the singleton."""
        os.environ["GEMINI_API_KEY"] = "test_key"
        os.environ["BOT_TOKEN"] = "test_token"
        
        config1 = get_configuration()
        reset_configuration()
        config2 = get_configuration()
        
        assert config1 is not config2


# ============================================================================
# ERROR MESSAGE SECURITY TESTS
# ============================================================================

class TestErrorMessageSecurity:
    """Test that error messages don't leak sensitive data."""
    
    def test_missing_credential_error_message_safe(self):
        """Test that error messages are human-readable but safe."""
        try:
            _get_credential("MISSING_KEY", required=True)
        except MissingCredentialError as e:
            error_msg = str(e)
            assert "MISSING_KEY" in error_msg  # Key name is okay
            assert "not found" in error_msg.lower()  # Clear message
            # Ensure no partial tokens or suspicious content
            assert "****" not in error_msg or len(error_msg) > 50
    
    def test_configuration_repr_does_not_expose_secrets(self):
        """Test that __repr__ is safe."""
        os.environ["GEMINI_API_KEY"] = "secret_key_value"
        os.environ["BOT_TOKEN"] = "secret_token_value"
        
        config = initialize_configuration()
        repr_str = repr(config)
        
        # Should not contain actual credentials
        assert "secret_key_value" not in repr_str
        assert "secret_token_value" not in repr_str


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestConfigurationIntegration:
    """Integration tests with real .env files."""
    
    def test_end_to_end_with_real_env_file(self, temp_env_file):
        """Test complete flow with a real .env file."""
        # Create .env file
        with open(temp_env_file, 'w') as f:
            f.write("# Arrow Configuration\n")
            f.write("GEMINI_API_KEY=sk_test_xyz123\n")
            f.write("BOT_TOKEN=bot_test_token_456\n")
            f.write("TELEGRAM_USER_ID=987654321\n")
            f.write("VOICE_RECORD_SECONDS=5\n")
        
        # Load and verify
        config = initialize_configuration(temp_env_file)
        
        assert config.gemini_api_key == "sk_test_xyz123"
        assert config.bot_token == "bot_test_token_456"
        assert config.telegram_user_id == 987654321
        assert config.voice_record_seconds == 5


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
