#!/usr/bin/env bash
# RunPod / Vast.ai GPU VM — vienkartinis setup.
# GPU: 1x RTX 4090 24GB, Ubuntu, volume >= 80GB.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== DiStyle Photo Pipeline — RunPod setup ==="

# System deps
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq git curl
fi

# Ollama (llava scoring)
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
ollama pull llava

# Server venv + CUDA torch
cd "$ROOT/server"
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt

# Client venv
cd "$ROOT/client"
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

# Env template reminder
if [[ ! -f "$ROOT/.env" ]]; then
  echo ""
  echo ">>> Nukopijuok .env i $ROOT/.env (WC + WP raktai)"
  echo ">>> Ir server/.env — ziurek server/.env.example"
fi

cat <<'EOF'

=== Paleidimas (3 terminalai arba tmux) ===

# 1) Ollama
ollama serve

# 2) AI serveris (FLUX Kontext ant CUDA)
cd server && source .venv/bin/activate
# Pirmas kartas: huggingface-cli login  (FLUX.1-Kontext-dev license)
python main.py

# 3) 3 etapu batch (sofos)
cd client && source .venv/bin/activate
python -m distyle_photo health
python -m distyle_photo preview-batch      # etapas 1: 2 sofos, be WP
python -m distyle_photo test-batch         # etapas 2: 10 sofu + WP (po OK)
python -m distyle_photo batch-all          # etapas 3: visos sofos (po OK)

EOF
