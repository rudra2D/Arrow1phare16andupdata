# Arrow Project - Configuration Quick Reference Card

## 🚀 5-Minute Setup

```bash
# 1. Create local .env from template
cp .env.example .env

# 2. Edit with your credentials
nano .env

# 3. Verify setup
python -c "from modules.config_loader import get_configuration; config = get_configuration(); print('✅ Configuration loaded successfully!')"
```

## 📦 Import & Use

```python
# Option 1: Get specific credentials (recommended)
from modules.config_loader import get_gemini_api_key, get_bot_token

api_key = get_gemini_api_key()
token = get_bot_token()

# Option 2: Get full configuration object
from modules.config_loader import get_configuration

config = get_configuration()
model = config.gemini_model
record_time = config.voice_record_seconds
```

## 🔑 Credentials Matrix

| Credential | Source | How to Get |
|-----------|--------|-----------|
| GEMINI_API_KEY | https://aistudio.google.com | Click "Get API Key" |
| BOT_TOKEN | Telegram @BotFather | Send `/newbot` command |
| TELEGRAM_USER_ID | Telegram @userinfobot | Bot sends your ID |
| Others | Your infrastructure | Configure as needed |

## ⚡ Common Operations

```python
# Load configuration (auto-initializes)
from modules.config_loader import get_configuration
config = get_configuration()

# Access credentials
gemini_key = config.gemini_api_key
bot_token = config.bot_token
model = config.gemini_model

# Check if optional config exists
if config.telegram_user_id:
    print(f"Telegram: {config.telegram_user_id}")

# Reset (testing/reconfiguration)
from modules.config_loader import reset_configuration
reset_configuration()

# Handle errors
from modules.config_loader import MissingCredentialError
try:
    config = get_configuration()
except MissingCredentialError as e:
    print(f"Setup required: {e}")
```

## 🛡️ Security Rules

| ✅ SAFE | ❌ UNSAFE |
|--------|----------|
| Use `get_configuration()` | Hardcode credentials |
| Read from `.env` file | Commit `.env` to git |
| Access `config.gemini_model` | Print `config.gemini_api_key` |
| Set environment variables | Share credentials in chat |
| Use `.gitignore` protection | Store secrets in comments |

## 📍 File Locations

```
.env                      ← Your actual secrets (never committed)
.env.example             ← Template for documentation
modules/config_loader.py ← The engine
CONFIG_SETUP_GUIDE.md    ← Full documentation
```

## 🆘 Troubleshooting

```python
# Test configuration
python -c "
from modules.config_loader import get_configuration
try:
    config = get_configuration()
    print('✅ All required credentials found')
except Exception as e:
    print(f'❌ Error: {e}')
"

# Check .env exists
ls -la .env

# View .env structure (without secrets)
grep -E '^[A-Z_]+=' .env | cut -d= -f1
```

## 🔄 Deployment Checklist

- [ ] `.env` created and filled
- [ ] `.env` in `.gitignore`
- [ ] `config_loader.py` in modules/
- [ ] No hardcoded credentials in code
- [ ] Tested locally: `python -c "from modules.config_loader import get_configuration; get_configuration()"`
- [ ] Environment variables set in target deployment
- [ ] Team has setup instructions

---

**TL;DR:** Copy `.env.example` to `.env`, fill in credentials, then use `get_configuration()` in your code. Never commit `.env`.
