#!/bin/bash

# ── Rhizomatic Research Agent — Linux Launcher ────────────────────────────────
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║        Rhizomatic Research Agent — Starting          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. Python virtual environment ────────────────────────────────────────────
if [ ! -d ".venv_linux" ]; then
    echo "[*] Creating virtual environment (.venv_linux)..."
    python3 -m venv .venv_linux
    if [ $? -ne 0 ]; then
        echo "[!] Failed to create venv. Install python3-venv:"
        echo "    sudo apt install python3-venv python3-dev build-essential"
        read -p "Press enter to exit..." && exit 1
    fi
fi

source .venv_linux/bin/activate
echo "[✓] Virtual environment active."

# ── 2. Environment config ─────────────────────────────────────────────────────
if [ ! -f "backend/.env" ]; then
    if [ -f "backend/.env.example" ]; then
        echo "[*] Creating backend/.env from .env.example..."
        cp backend/.env.example backend/.env
    else
        echo "[!] Warning: backend/.env not found."
    fi
fi

# ── 3. Core Python dependencies ───────────────────────────────────────────────
REQ_HASH_FILE=".venv_linux/.req_hash"
CURRENT_HASH=$(md5sum backend/requirements.txt 2>/dev/null | cut -d' ' -f1)
STORED_HASH=$(cat "$REQ_HASH_FILE" 2>/dev/null)

if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
    echo "[*] Installing / updating Python dependencies..."
    pip install --upgrade pip -q
    pip install -r backend/requirements.txt
    if [ $? -eq 0 ]; then
        echo "$CURRENT_HASH" > "$REQ_HASH_FILE"
        echo "[✓] Dependencies installed."
    else
        echo "[!] Dependency installation failed."
        read -p "Press enter to exit..." && exit 1
    fi
else
    echo "[✓] Dependencies up to date."
fi

# ── 4. Spacy language model (required by Kokoro TTS) ─────────────────────────
if ! python3 -c "import spacy; spacy.load('en_core_web_sm')" &>/dev/null; then
    echo "[*] Downloading spacy en_core_web_sm (required by Kokoro TTS)..."
    python3 -m spacy download en_core_web_sm -q
    echo "[✓] Spacy model ready."
else
    echo "[✓] Spacy model ready."
fi

# ── 5. Kokoro TTS voice files ─────────────────────────────────────────────────
VOICES_DIR="backend/models/kokoro/voices"
VOICE_MARKER="$VOICES_DIR/af_bella.pt"

if [ ! -f "$VOICE_MARKER" ]; then
    echo "[*] Downloading Kokoro TTS voice files from HuggingFace..."
    mkdir -p "$VOICES_DIR"
    python3 - <<'PYEOF'
from huggingface_hub import hf_hub_download
import pathlib, sys

dest = pathlib.Path("backend/models/kokoro")
voices = [
    "af_bella","af_nicole","af_sarah","af_sky",
    "am_adam","am_michael",
    "bf_emma","bf_isabella","bm_george","bm_lewis"
]
ok = True
for v in voices:
    try:
        hf_hub_download("hexgrad/Kokoro-82M", f"voices/{v}.pt", local_dir=str(dest))
        print(f"  [✓] {v}.pt")
    except Exception as e:
        print(f"  [!] Failed {v}.pt: {e}")
        ok = False
sys.exit(0 if ok else 1)
PYEOF
    if [ $? -eq 0 ]; then
        echo "[✓] Kokoro voice files ready."
    else
        echo "[!] Some voice files failed to download. TTS will fall back to browser speech."
    fi
else
    echo "[✓] Kokoro TTS voice files ready."
fi

# ── 6. BERT model check (informational) ──────────────────────────────────────
BERT_ENABLED=$(grep "^BERT_ENABLED" backend/.env 2>/dev/null | cut -d'=' -f2 | tr -d ' ')
if [ "$BERT_ENABLED" = "true" ]; then
    if python3 -c "import sentence_transformers, umap, hdbscan" &>/dev/null; then
        echo "[✓] BERT Semantic Topography enabled."
    else
        echo "[!] BERT_ENABLED=true but dependencies missing. Run:"
        echo "    pip install sentence-transformers umap-learn hdbscan"
    fi
fi

# ── 7. Ollama service + model ─────────────────────────────────────────────────
MODEL_NAME=$(grep "^OLLAMA_MODEL" backend/.env 2>/dev/null | cut -d'=' -f2 | tr -d ' ')
[ -z "$MODEL_NAME" ] && MODEL_NAME="mistral-large-3:675b-cloud"

echo "[*] Checking Ollama at http://localhost:11434..."
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "[!] Ollama not running. Attempting to start via systemd..."
    sudo systemctl start ollama 2>/dev/null
    sleep 3
fi

if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    if ollama list 2>/dev/null | grep -q "$MODEL_NAME"; then
        echo "[✓] Ollama running. Model '$MODEL_NAME' ready."
    else
        echo "[*] Pulling model '$MODEL_NAME' (this may take a while)..."
        ollama pull "$MODEL_NAME"
    fi
else
    echo "[!] Ollama not responding. Start it with: ollama serve"
    echo "    The app may fail to process queries without it."
fi

# ── 8. Launch ─────────────────────────────────────────────────────────────────
echo ""
echo "[*] Starting Rhizomatic Research Agent at http://localhost:8000"
echo ""
python3 launcher.py

if [ $? -ne 0 ]; then
    echo ""
    echo "[!] Application exited with an error."
    read -p "Press enter to exit..."
fi
