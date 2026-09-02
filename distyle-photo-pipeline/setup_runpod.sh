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

# Ollama optional — default VISION_USE_OLLAMA=0 (heuristics only).
# GPU reserved for FLUX. Install only if you later enable VISION_USE_OLLAMA=1.
# if ! command -v ollama >/dev/null 2>&1; then
#   curl -fsSL https://ollama.com/install.sh | sh
# fi
# ollama pull llava

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

=== Paleidimas (2 terminalai) ===
# GPU = tik FLUX. Scoring = heuristics (Ollama nereikia).

# 1) AI serveris
cd server && source .venv/bin/activate
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
python main.py

# 2) Pipeline
cd client && source .venv/bin/activate
python -m distyle_photo health
python -m distyle_photo preview-batch
python -m distyle_photo test-batch
python -m distyle_photo batch-all

EOF
