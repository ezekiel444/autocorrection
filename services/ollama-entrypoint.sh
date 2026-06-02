#!/bin/bash
# Start Ollama server in background, pull the configured model, then keep running.

# Start ollama serve in background
ollama serve &
SERVER_PID=$!

# Wait for server to be ready
echo "Waiting for Ollama server to start..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:11434/ > /dev/null 2>&1; then
        echo "Ollama server is ready."
        break
    fi
    sleep 2
done

# Check if model is already available
MODEL_NAME="${MODEL_NAME:-llama3.2:3b}"
echo "Checking model: $MODEL_NAME"

if ollama list 2>/dev/null | grep -q "$MODEL_NAME"; then
    echo "Model $MODEL_NAME already available."
else
    echo "Model $MODEL_NAME not found locally."
    echo "Attempting to pull (requires network access)..."
    if ollama pull "$MODEL_NAME" 2>&1; then
        echo "Model $MODEL_NAME pulled successfully."
    else
        echo "WARNING: Failed to pull model $MODEL_NAME."
        echo "The LLM container has no internet access by design."
        echo ""
        echo "To fix this, run the model pull BEFORE starting with network isolation:"
        echo "  1. podman-compose down"
        echo "  2. podman run --rm -v autocorrection-tw_models_data:/root/.ollama --entrypoint bash ollama/ollama -c 'ollama serve & sleep 5 && ollama pull $MODEL_NAME'"
        echo "  3. podman-compose up -d"
        echo ""
        echo "The model will persist in the volume for future starts."
    fi
fi

# Keep the server running in foreground
wait $SERVER_PID
