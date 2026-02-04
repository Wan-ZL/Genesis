# Ollama Local Model Setup

This guide explains how to set up and use Ollama for local LLM inference with the AI Assistant.

## Overview

Ollama provides local inference with open-source models like Llama 3.2, Mistral, and others. The AI Assistant integrates Ollama as a fallback when cloud APIs (OpenAI/Claude) are unavailable, or as the primary model in "local-only" mode.

## Benefits

- **Privacy**: Conversations never leave your machine
- **Offline**: Works without internet connection
- **Cost**: No API costs for local inference
- **Speed**: Low latency for local models

## Installation

### 1. Install Ollama

Visit [ollama.ai](https://ollama.ai) or use Homebrew on macOS:

```bash
brew install ollama
```

### 2. Start Ollama Service

```bash
ollama serve
```

By default, Ollama runs on `http://localhost:11434`.

### 3. Pull a Model

```bash
# Recommended: Llama 3.2 3B (fast, good quality)
ollama pull llama3.2:3b

# For better quality (requires more resources):
ollama pull llama3.2:70b

# Other options:
ollama pull mistral
ollama pull codellama
ollama pull mixtral
```

### 4. Verify Installation

```bash
# List installed models
ollama list

# Test a model
ollama run llama3.2:3b "Hello, how are you?"
```

## Configuration

### Environment Variables

Set these in your environment or `.env` file:

```bash
# Ollama endpoint (default: http://localhost:11434)
OLLAMA_HOST=http://localhost:11434

# Default model (default: llama3.2:3b)
OLLAMA_MODEL=llama3.2:3b

# Enable/disable Ollama (default: true)
OLLAMA_ENABLED=true

# Request timeout in seconds (default: 120)
OLLAMA_TIMEOUT=120
```

### Settings API

Configure Ollama via the Settings API:

```bash
# Get current settings
curl http://127.0.0.1:8080/api/settings

# Update Ollama model
curl -X POST http://127.0.0.1:8080/api/settings \
  -H "Content-Type: application/json" \
  -d '{"ollama_model": "mistral"}'

# Enable local-only mode
curl -X POST http://127.0.0.1:8080/api/ollama/local-only \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### Ollama-Specific Endpoints

```bash
# Check Ollama status
curl http://127.0.0.1:8080/api/ollama/status

# List available local models
curl http://127.0.0.1:8080/api/ollama/models

# Select a model
curl -X POST http://127.0.0.1:8080/api/ollama/model \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2:3b"}'
```

## Fallback Behavior

The AI Assistant uses this fallback chain:

1. **Primary API** (Claude or OpenAI based on config)
2. **Secondary API** (the other cloud API)
3. **Ollama** (local fallback)

When cloud APIs fail:
- Rate limited → Wait and retry, or fall back
- Network error → Automatically use Ollama
- API unavailable → Automatically use Ollama

### Local-Only Mode

Enable local-only mode to **always** use Ollama, ignoring cloud APIs:

```bash
curl -X POST http://127.0.0.1:8080/api/ollama/local-only \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

Use cases:
- Privacy-sensitive conversations
- Offline operation
- Cost reduction

## Model Recommendations

| Model | Size | Use Case |
|-------|------|----------|
| `llama3.2:3b` | ~2GB | Fast responses, general use |
| `llama3.2:70b` | ~40GB | High quality, needs GPU |
| `mistral` | ~4GB | Good balance |
| `codellama` | ~4GB | Code generation |
| `mixtral` | ~26GB | Best quality, needs resources |

## Tool Calling Support

Newer models (Llama 3+, Mistral, Mixtral) support tool calling. The assistant automatically detects model capabilities and:
- Enables tools for capable models
- Gracefully degrades for models without tool support

## Troubleshooting

### Ollama not detected

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start if not running
ollama serve
```

### Model not found

```bash
# List installed models
ollama list

# Pull the model if missing
ollama pull llama3.2:3b
```

### Slow responses

- Use a smaller model (`llama3.2:3b` instead of `70b`)
- Ensure sufficient RAM (8GB+ recommended)
- Use GPU acceleration if available

### Connection refused

Check Ollama host setting:
```bash
# Default
curl http://localhost:11434/api/tags

# Custom port
export OLLAMA_HOST=http://localhost:CUSTOM_PORT
```

## Health Monitoring

The assistant health endpoint includes Ollama status:

```bash
curl http://127.0.0.1:8080/api/health
```

Response includes:
```json
{
  "status": "healthy",
  "ollama_available": true
}
```

Detailed status:
```bash
curl http://127.0.0.1:8080/api/status
```

## Security Considerations

- Ollama runs locally and doesn't send data externally
- The assistant logs which model is used for each request
- Local-only mode ensures no cloud API calls are made
- No authentication is required for local Ollama (runs on localhost)
