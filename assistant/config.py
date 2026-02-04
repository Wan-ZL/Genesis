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

# Active model (for logging/display)
MODEL = CLAUDE_MODEL if USE_CLAUDE else OPENAI_MODEL

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

# Context window management
# Number of recent messages to keep verbatim in context
RECENT_MESSAGES_VERBATIM = 20
# Number of older messages to summarize as one batch
MESSAGES_PER_SUMMARY_BATCH = 10
# Maximum characters for a summary
MAX_SUMMARY_LENGTH = 500

# Ollama settings for local model fallback
# Ollama provides local inference with models like Llama, Mistral, etc.
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")  # Fast local model
OLLAMA_ENABLED = os.getenv("OLLAMA_ENABLED", "true").lower() == "true"
# Timeout for Ollama requests (local inference can be slower)
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

# Repository analysis settings
# Colon-separated list of directories the assistant can read
# Default: Genesis project root (allows self-analysis)
REPOSITORY_PATHS = os.getenv("REPOSITORY_PATHS", str(BASE_DIR.parent))
# Maximum file size to read (in bytes)
REPOSITORY_MAX_FILE_SIZE = int(os.getenv("REPOSITORY_MAX_FILE_SIZE", str(1024 * 1024)))  # 1MB
