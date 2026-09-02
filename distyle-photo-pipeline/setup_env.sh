#!/usr/bin/env bash
# RunPod / Jupyter: .env failus lengviau upload'inti BE tasko,
# tada paleisti sia komanda.
#
# Naudojimas:
#   bash setup_env.sh
#
# Tikimasi siu failu (bet kuris variantas):
#   env.txt  /  dotenv  /  root.env     →  .env
#   server-env.txt  /  server.env.txt  /  server_env.txt  →  server/.env
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "=== DiStyle .env setup ==="

# --- root .env ---
if [[ -f .env ]]; then
  echo "[ok] .env jau yra"
else
  for cand in env.txt dotenv root.env .env.upload; do
    if [[ -f "$cand" ]]; then
      mv "$cand" .env
      echo "[ok] $cand → .env"
      break
    fi
  done
fi

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "[!] sukurtas .env is .env.example — IRENGIK WC/WP/HF raktus: nano .env"
  else
    echo "[!] nera .env — upload'ink env.txt i $ROOT ir paleisk is naujo"
  fi
else
  echo "[ok] root .env ready: $ROOT/.env"
fi

# --- server/.env ---
mkdir -p server
if [[ -f server/.env ]]; then
  echo "[ok] server/.env jau yra"
else
  for cand in server-env.txt server.env.txt server_env.txt server.env .env.server; do
    if [[ -f "$cand" ]]; then
      mv "$cand" server/.env
      echo "[ok] $cand → server/.env"
      break
    fi
    if [[ -f "server/$cand" ]]; then
      mv "server/$cand" server/.env
      echo "[ok] server/$cand → server/.env"
      break
    fi
  done
fi

if [[ ! -f server/.env ]]; then
  if [[ -f server/.env.example ]]; then
    cp server/.env.example server/.env
    echo "[!] sukurtas server/.env is example — IRENGIK HF_TOKEN: nano server/.env"
  else
    echo "[!] nera server/.env — upload'ink server-env.txt"
  fi
else
  echo "[ok] server .env ready: $ROOT/server/.env"
fi

echo ""
echo "=== Redaguoti ==="
echo "  nano $ROOT/.env"
echo "  nano $ROOT/server/.env"
echo ""
echo "=== Greitas check (be secretu) ==="
grep -E '^(WC_URL|WP_USER|AI_SERVER|LOCAL_IMAGE_|VISION_|HF_TOKEN)=' .env 2>/dev/null | sed 's/=.*/=***/' || true
grep -E '^(LOCAL_IMAGE_|VISION_|HF_TOKEN|CUTOUT_)=' server/.env 2>/dev/null | sed 's/\(HF_TOKEN=\).*/\1***/' || true
echo ""
echo "Baigta."
