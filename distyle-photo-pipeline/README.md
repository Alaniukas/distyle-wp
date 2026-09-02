# DiStyle Photo Pipeline

Automatinis sofų nuotraukų standartizavimas distyle.lt WooCommerce parduotuvei.

## Greitas startas (Windows)

### 1. Diegimas (vieną kartą)
```powershell
.\setup_local_digroup.ps1
ollama pull moondream
```

### 2. Paleidimas (3 langai)

**Langas 1 — Ollama** (dažnai jau veikia fone):
```powershell
ollama serve
```

**Langas 2 — AI serveris:**
```powershell
cd server
.venv\Scripts\activate
python main.py
```

**Langas 3 — Pipeline:**
```powershell
cd client
.venv\Scripts\activate
python -m distyle_photo health
python -m distyle_photo scan --limit 10
python -m distyle_photo run --dry-run --limit 10 --skip-on-sale --non-standard-only
```

### 3. Rezultatai
Dry-run nuotraukos: `client/output/product_<ID>_studio.webp`

## Dokumentacija
- [LOKALUS_SETUP_PILNAS.md](LOKALUS_SETUP_PILNAS.md) — pilnas vadovas
