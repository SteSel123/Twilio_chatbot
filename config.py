"""Application configuration from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def get_secret(name: str, default: str = "") -> str:
    if os.getenv("AZURE_KEY_VAULT_URL", ""):
        try:
            from platform.secrets import get_secret as _vault_get

            return _vault_get(name, default)
        except ImportError:
            pass
    return os.getenv(name, default)
DOCS_DIR = BASE_DIR / "docs"
MEMORY_DIR = BASE_DIR / ".conversation_memory"
DATA_DIR = BASE_DIR / ".user_data"
DB_PATH = DATA_DIR / "cases.db"
UPLOADS_DIR = DATA_DIR / "uploads"
VECTOR_DB_DIR = DATA_DIR / "vector_db"

# Environment
ENV = os.getenv("ENV", "development")
IS_PRODUCTION = ENV == "production"

# Data retention (hours) — overridden by subscription tier when billing enabled
DATA_RETENTION_HOURS = int(os.getenv("DATA_RETENTION_HOURS", "12"))
RETENTION_TIERS = {
    "free": int(os.getenv("RETENTION_HOURS_FREE", "12")),
    "standard": int(os.getenv("RETENTION_HOURS_STANDARD", "168")),
    "premium": int(os.getenv("RETENTION_HOURS_PREMIUM", "720")),
}

DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "default")
DEFAULT_REGION = os.getenv("DEFAULT_REGION", "eu")
ADMIN_API_KEY = get_secret("ADMIN_API_KEY", "")
SERVICE_API_KEY = get_secret("SERVICE_API_KEY", "")

# Twilio
TWILIO_ACCOUNT_SID = get_secret("TWILIO_ACCOUNT_SID", "")
TWILIO_API_KEY = get_secret("TWILIO_API_KEY", "")
TWILIO_API_SECRET = get_secret("TWILIO_API_SECRET", "")
TWILIO_AUTH_TOKEN = get_secret("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

# Webhooks & security
PORT = int(os.getenv("PORT", "5000"))
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")
ENFORCE_HTTPS = os.getenv("ENFORCE_HTTPS", "1" if IS_PRODUCTION else "0") == "1"
ENFORCE_TWILIO_HMAC = os.getenv("ENFORCE_TWILIO_HMAC", "1" if IS_PRODUCTION else "0") == "1"
WEBHOOK_ALLOWED_IPS = os.getenv("WEBHOOK_ALLOWED_IPS", "")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
USE_REDIS_QUEUE = os.getenv("USE_REDIS_QUEUE", "1" if IS_PRODUCTION else "0") == "1"

# Database — PostgreSQL in production, SQLite for local dev
DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)

# External APIs
TAVILY_API_KEY = get_secret("TAVILY_API_KEY", "")
TAVILY_SEARCH_DEPTH = os.getenv("TAVILY_SEARCH_DEPTH", "basic")
GOOGLE_MAPS_API_KEY = get_secret("GOOGLE_MAPS_API_KEY", "")

# LLM — ollama (dev) or openai (production latency target)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai" if IS_PRODUCTION else "ollama")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_FAST_MODEL = os.getenv("OLLAMA_FAST_MODEL", "llama3.2")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava:latest")
SETUP_USE_LLM_DEMO = os.getenv("SETUP_USE_LLM_DEMO", "0") == "1"
SETUP_VISION_MAX_PIXELS = int(os.getenv("SETUP_VISION_MAX_PIXELS", "1024"))
OLLAMA_VISION_TIMEOUT = int(os.getenv("OLLAMA_VISION_TIMEOUT", "180"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "350"))
OPENAI_API_KEY = get_secret("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Vector RAG
USE_VECTOR_RAG = os.getenv("USE_VECTOR_RAG", "1") == "1"

# Stripe billing
STRIPE_SECRET_KEY = get_secret("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = get_secret("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_STANDARD = os.getenv("STRIPE_PRICE_STANDARD", "")
STRIPE_PRICE_PREMIUM = os.getenv("STRIPE_PRICE_PREMIUM", "")
STRIPE_PRICE_STARTER = os.getenv("STRIPE_PRICE_STARTER", STRIPE_PRICE_STANDARD)
STRIPE_PRICE_GROWTH = os.getenv("STRIPE_PRICE_GROWTH", STRIPE_PRICE_PREMIUM)

# Calendar & notifications
GOOGLE_CALENDAR_CREDENTIALS_JSON = get_secret("GOOGLE_CALENDAR_CREDENTIALS_JSON", "")
GOOGLE_OAUTH_CLIENT_ID = get_secret("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_OAUTH_CLIENT_SECRET = get_secret("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

# Landing page integration
LANDING_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "LANDING_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]
LANDING_URL = os.getenv(
    "LANDING_URL",
    next(
        (u for u in reversed(LANDING_ALLOWED_ORIGINS) if "vercel.app" in u),
        "https://whatsapp-saas-landing-beryl.vercel.app",
    ),
)

# Observability
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

# Human handoff
HANDOFF_EMAIL = os.getenv("HANDOFF_EMAIL", "")
HANDOFF_WEBHOOK_URL = os.getenv("HANDOFF_WEBHOOK_URL", "")

# Owner notification e-mail (conversation summaries)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = get_secret("SMTP_USER", "")
SMTP_PASSWORD = get_secret("SMTP_PASSWORD", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "1") == "1"
NOTIFY_FROM_EMAIL = os.getenv("NOTIFY_FROM_EMAIL", SMTP_USER or "noreply@appassist.nl")

# Consent & legal
PRIVACY_POLICY_URL = os.getenv("PRIVACY_POLICY_URL", "")
TERMS_URL = os.getenv("TERMS_URL", "")

# Agent limits
MAX_HISTORY_TURNS = 6
MAX_DOC_CHARS = 4000
MAX_SEARCH_RESULTS = 3
MAX_SEARCH_CONTEXT_CHARS = 2500

# MCP server (Cursor, OpenAI Remote MCP, admin copilot)
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
MCP_API_KEY = get_secret("MCP_API_KEY", "")
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")

# Flask sessions (admin login)
FLASK_SECRET_KEY = get_secret("FLASK_SECRET_KEY", "")
