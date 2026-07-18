#!/bin/bash
# Entrypoint for the API container.
# Starts Ollama (CPU-only) in the background, waits for it to be ready,
# pulls the nomic-embed-text model, then launches uvicorn.

set -e

# Upgrade tenacity if needed (compat with Python 3.12 for dramatiq-pg)
pip install --upgrade tenacity -q 2>/dev/null || true

# Start Ollama server in background
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
for i in $(seq 1 30); do
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo "Ollama is ready"
        break
    fi
    echo "Waiting for Ollama... ($i/30)"
    sleep 1
done

# Pull the embedding model
echo "Pulling nomic-embed-text..."
ollama pull nomic-embed-text
echo "nomic-embed-text ready"

# Execute the main command (uvicorn or dramatiq)
exec "$@"