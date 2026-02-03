"""AI Assistant configuration."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load secrets from .claude/ env files
SECRETS_DIR = Path(__file__).parent.parent / ".claude"

# Load OpenAI key
openai_secrets = SECRETS_DIR / "openai-key-secrets.env"
if openai_secrets.exists():
    load_dotenv(openai_secrets)

# Load Anthropic key
anthropic_secrets = SECRETS_DIR / "anthropic-key-secrets.env"
if anthropic_secrets.exists():
    load_dotenv(anthropic_secrets)

# API settings - prefer Anthropic/Claude, fallback to OpenAI
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Model selection based on available API
USE_CLAUDE = bool(ANTHROPIC_API_KEY)
CLAUDE_MODEL = "claude-sonnet-4-20250514"  # Claude Sonnet for good balance of quality/speed
OPENAI_MODEL = "gpt-4o"

# Server settings
HOST = "127.0.0.1"
PORT = 8080

# Paths
BASE_DIR = Path(__file__).parent
DATABASE_PATH = BASE_DIR / "memory" / "conversations.db"
FILES_PATH = BASE_DIR / "memory" / "files"

# Ensure directories exist
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
FILES_PATH.mkdir(parents=True, exist_ok=True)
