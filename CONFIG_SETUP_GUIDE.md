# Arrow Project - Secure Configuration & Secret Management

## 📋 Overview

This guide explains the production-grade configuration and secret management system for the Arrow Project. The system ensures that sensitive credentials (API keys, bot tokens, etc.) are **never exposed** in code or version control, while maintaining seamless support for multiple deployment environments.

---

## 🏗️ Architecture

### Three-Layer Configuration System

```
Layer 1: .env File (Local Secrets)
         ↓
Layer 2: Environment Variables (System-Level)
         ↓
Layer 3: Google Colab Secrets (Cloud Fallback)
         ↓
Layer 4: Defaults (Non-sensitive values)
```

### File Structure

```
Arrow1phare16andupdata/
├── .env                          # 🔐 ACTUAL SECRETS (local only, never committed)
├── .env.example                  # 📖 Template for documentation
├── .gitignore                    # ✅ Prevents .env from being committed
├── modules/
│   └── config_loader.py          # 🔑 Secure configuration engine
├── config.py                     # Legacy configuration (still works)
└── [other files...]
```

---

## 🚀 Quick Start

### Step 1: Initialize Local .env File

```bash
# Copy the template to create your local .env
cp .env.example .env

# Edit .env with your actual credentials
nano .env  # or use your preferred editor
```

### Step 2: Fill in Your Credentials

Edit `.env` and replace placeholders with actual values:

```env
# Example .env file with real values
GEMINI_API_KEY=AIzaSyD...your_actual_key...
BOT_TOKEN=123456789:ABCDEFGH...your_actual_token...
TELEGRAM_USER_ID=987654321
ADMIN_CHAT_ID=987654321
```

### Step 3: Use Configuration in Your Code

```python
from modules.config_loader import get_configuration, get_gemini_api_key

# Option A: Use convenience getters
api_key = get_gemini_api_key()
bot_token = get_gemini_api_key()

# Option B: Use full configuration object
config = get_configuration()
print(f"Using Gemini model: {config.gemini_model}")
print(f"Voice recording: {config.voice_record_seconds} seconds")
```

---

## 🔐 Security Features

### 1. **No Credential Exposure in Logs**
```python
# ❌ DANGEROUS - Don't do this
print(f"Using key: {api_key}")  # LEAKS credentials!

# ✅ SAFE - This is allowed
print(f"Using model: {config.gemini_model}")  # Non-sensitive data only
```

### 2. **Automatic .env Protection**
The `.gitignore` file ensures `.env` is never committed:
```
.env                  # Never tracked
.env.*.local         # Environment-specific files protected
```

### 3. **Meaningful Error Messages Without Token Leaks**
```python
# When credentials are missing, you get clear error messages:
# "Required credential 'GEMINI_API_KEY' not found. 
#  Please set GEMINI_API_KEY in your .env file or environment variables."

# Notice: No partial keys printed, no sensitive data exposed
```

### 4. **Type-Safe Configuration**
```python
# All values are properly typed and validated
config = get_configuration()

# Type hints work in your IDE
api_key: str = config.gemini_api_key          # String type
user_id: Optional[int] = config.telegram_user_id  # Optional integer
record_seconds: int = config.voice_record_seconds  # Integer
```

---

## 🌍 Deployment Environments

### Local Development
```python
# Uses .env file in project root
config = initialize_configuration()
```

### Docker / CI/CD
```bash
# Set environment variables before running
export GEMINI_API_KEY="your_key_here"
export BOT_TOKEN="your_token_here"
docker run my-arrow-app
```

### Google Colab
```python
# Automatically falls back to Colab secrets
from modules.config_loader import initialize_configuration

config = initialize_configuration()
# Will use google.colab.userdata.get() if .env not available
```

### Cloud Platforms (AWS, GCP, Azure)
```python
# Set environment variables in your cloud provider's dashboard
# config_loader.py automatically detects and uses them

config = initialize_configuration()
```

---

## 📚 Configuration Reference

### Core LLM Configuration

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `GEMINI_API_KEY` | String | ✅ Yes | API key for Google Gemini LLM |
| `GEMINI_MODEL` | String | ❌ No | Model identifier (default: `gemini-1.5-pro`) |

**How to get GEMINI_API_KEY:**
1. Visit https://aistudio.google.com
2. Click "Get API Key"
3. Create new API key or use existing
4. Copy and paste into `.env`

### Telegram Bot Integration

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `BOT_TOKEN` | String | ✅ Yes | Telegram bot token from @BotFather |
| `TELEGRAM_USER_ID` | Integer | ❌ No | Your Telegram user ID (numeric) |
| `ADMIN_CHAT_ID` | Integer | ❌ No | Admin chat ID (usually same as TELEGRAM_USER_ID) |

**How to get BOT_TOKEN:**
1. Open Telegram and search for `@BotFather`
2. Send `/newbot` command
3. Follow instructions and receive your token
4. Copy and paste into `.env`

**How to get TELEGRAM_USER_ID:**
1. Message `@userinfobot` on Telegram
2. Bot sends your numeric ID
3. Add to `.env` as `TELEGRAM_USER_ID=<your_id>`

### Voice Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `VOICE_RECORD_SECONDS` | Integer | 7 | Duration of voice recording sessions |
| `VOICE_LANGUAGE` | String | en-US | Language code for voice I/O |

### Private Storage & File Routing

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `PRIVATE_SERVER_UPLOAD_URL` | String | ❌ No | Endpoint for secure file uploads |
| `PRIVATE_BACKUP_UPLOAD_URL` | String | ❌ No | Backup storage endpoint |
| `PRIVATE_STORAGE_AUTH_TOKEN` | String | ❌ No | Authentication token for storage |

### Camera & Hardware

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `CAMERA_RTSP_URL` | String | ❌ No | RTSP feed URL for Wi-Fi camera |

---

## 💻 API Reference

### Initialization Functions

#### `initialize_configuration(env_path=None) -> ArrowConfiguration`
Initialize the entire configuration system from scratch.

```python
from modules.config_loader import initialize_configuration

config = initialize_configuration()
# or with custom path:
config = initialize_configuration(env_path="/path/to/.env")
```

#### `get_configuration() -> ArrowConfiguration`
Get the current configuration (singleton pattern). Initializes automatically if needed.

```python
from modules.config_loader import get_configuration

config = get_configuration()
api_key = config.gemini_api_key
```

#### `reset_configuration() -> None`
Clear cached configuration. Useful for testing or reconfiguration.

```python
from modules.config_loader import reset_configuration

reset_configuration()
# Next call to get_configuration() will reinitialize
```

### Convenience Getters

#### `get_gemini_api_key() -> str`
```python
from modules.config_loader import get_gemini_api_key

key = get_gemini_api_key()  # Returns string or raises MissingCredentialError
```

#### `get_bot_token() -> str`
```python
from modules.config_loader import get_bot_token

token = get_bot_token()  # Returns string or raises MissingCredentialError
```

---

## 🛠️ Advanced Usage

### Updating Configuration in Code

```python
from modules.config_loader import get_configuration

config = get_configuration()

# Access individual credentials
print(f"API Key: (hidden for security)")
print(f"Bot Token: (hidden for security)")
print(f"Model: {config.gemini_model}")
print(f"Voice Language: {config.voice_language}")

# Type-safe access
if config.telegram_user_id:
    print(f"Telegram User: {config.telegram_user_id}")
```

### Error Handling

```python
from modules.config_loader import (
    get_configuration,
    MissingCredentialError,
    ConfigurationError
)

try:
    config = get_configuration()
    api_key = config.gemini_api_key
except MissingCredentialError as e:
    print(f"Configuration error: {e}")
    print("Please set up your .env file")
except ConfigurationError as e:
    print(f"Unexpected error: {e}")
```

### Integrating New API Keys

When adding support for new services (OpenAI, Slack, etc.):

1. **Update `.env.example`** with the new slot:
   ```env
   # [FUTURE_API_EXTENSIONS] - NEW SERVICE INTEGRATION
   OPENAI_API_KEY=your_openai_api_key_here
   ```

2. **Update `.env`** with placeholder:
   ```env
   OPENAI_API_KEY=
   ```

3. **Add to `ArrowConfiguration` dataclass** in `config_loader.py`:
   ```python
   openai_api_key: Optional[str] = None
   ```

4. **Add to `initialize_configuration()` function**:
   ```python
   openai_api_key=_get_credential("OPENAI_API_KEY", required=False),
   ```

5. **Add convenience getter** (optional):
   ```python
   def get_openai_api_key() -> str:
       config = get_configuration()
       if not config.openai_api_key:
           raise MissingCredentialError("OPENAI_API_KEY not configured")
       return config.openai_api_key
   ```

---

## 🧪 Testing

### Unit Testing with Config Loader

```python
import pytest
from modules.config_loader import reset_configuration, initialize_configuration

def test_config_loading():
    reset_configuration()
    config = initialize_configuration()
    
    assert config.gemini_model == "gemini-1.5-pro"
    assert config.voice_record_seconds == 7
    assert config.gemini_api_key is not None

def test_missing_critical_credential():
    with pytest.raises(MissingCredentialError):
        # This will fail if GEMINI_API_KEY is not set
        config = initialize_configuration()
```

---

## ⚠️ Common Issues & Solutions

### Issue: "MissingCredentialError: Required credential 'GEMINI_API_KEY' not found"

**Cause:** The GEMINI_API_KEY is not set in `.env` or environment variables.

**Solution:**
```bash
# 1. Copy the template
cp .env.example .env

# 2. Edit .env and add your actual key
nano .env

# 3. Verify the file exists
cat .env
```

### Issue: "Permission denied reading .env file"

**Cause:** File permissions are too restrictive.

**Solution:**
```bash
# Fix permissions
chmod 600 .env

# Or if running as different user
sudo chown $USER .env
```

### Issue: Works locally but fails in Docker/Cloud

**Cause:** The `.env` file is not being passed to the container.

**Solution:**
```bash
# For Docker, mount the file or use --env-file
docker run --env-file .env my-arrow-app

# For cloud, set environment variables in provider dashboard
# AWS: Use .env file or Systems Manager Parameter Store
# GCP: Use Cloud Secret Manager or environment variables
# Azure: Use Key Vault or app configuration
```

### Issue: Google Colab can't find credentials

**Cause:** Secrets not stored in Colab or wrong secret name.

**Solution:**
```python
# In Colab, use the Secrets pane (🔑 icon in left sidebar)
# Store secrets with exact names:
# - GEMINI_API_KEY
# - BOT_TOKEN
# - etc.

# Then run:
from modules.config_loader import initialize_configuration
config = initialize_configuration()
```

---

## 🔒 Security Best Practices

### ✅ DO:
- ✅ Keep `.env` in `.gitignore`
- ✅ Use environment variables in production
- ✅ Rotate API keys regularly
- ✅ Use strong, unique bot tokens
- ✅ Back up `.env` securely (encrypted)
- ✅ Never share `.env` via email or chat
- ✅ Use config_loader for all credential access

### ❌ DON'T:
- ❌ Commit `.env` to repository
- ❌ Print API keys in logs
- ❌ Hardcode credentials in code
- ❌ Share `.env` files via insecure channels
- ❌ Use same credentials across environments
- ❌ Expose credentials in error messages
- ❌ Store credentials in comments

---

## 📞 Support

For issues or questions about the configuration system:

1. Check this documentation thoroughly
2. Review error messages for clues
3. Verify `.env` file is properly formatted
4. Test with `python -c "from modules.config_loader import get_configuration; print('OK')"`

---

## 📋 Checklist

Before deploying to production:

- [ ] `.env` file created and filled with real credentials
- [ ] `.env` is listed in `.gitignore`
- [ ] Tested configuration loading locally
- [ ] All critical credentials validated (GEMINI_API_KEY, BOT_TOKEN)
- [ ] No credentials hardcoded in any Python files
- [ ] Environment variables set up in target deployment
- [ ] Backup of `.env` stored securely
- [ ] Team members have instructions for setup
- [ ] No `.env` file in git history (use `git rm --cached .env` if needed)

---

**Version:** 1.0  
**Last Updated:** 2025-06-12  
**Maintained By:** Arrow Project Team
