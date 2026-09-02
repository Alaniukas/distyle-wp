# DiStyle nuotraukų pipeline — PILNAS lokalaus setup vadovas

> **Skirta:** kitam agentui / developeriui, kuris ant Alano PC (Windows 11)  
> **Tikslas:** paruošti ir paleisti pipeline lokaliai su Ollama.  
> **OpenAI nereikia. Supabase nereikia. VPS nereikia** (lokaliam pilotui).

## Architektūra

```
Langas 3: Python klientas (client/)
    ├── distyle.lt WooCommerce REST API
    └── Langas 2: AI serveris http://127.0.0.1:8765
            ├── POST /vision/score
            ├── POST /cutout
            └── Langas 1: Ollama http://127.0.0.1:11434 (moondream)
```

## Projekto kelias

```
C:\Users\Alanas\Desktop\digroup\distyle WP\distyle-photo-pipeline\
```

## Diegimas

```powershell
cd "C:\Users\Alanas\Desktop\digroup\distyle WP\distyle-photo-pipeline"
.\setup_local_digroup.ps1
ollama pull moondream
```

## .env

- `distyle-photo-pipeline/.env` — WC + WP + AI server (jau paruošta)
- `distyle-photo-pipeline/server/.env` — CUTOUT_API_KEY + Ollama (jau paruošta)

**Svarbu:** `AI_SERVER_API_KEY` (client) = `CUTOUT_API_KEY` (server) = `local-test-key`

## CLI komandos

```powershell
cd client
.venv\Scripts\activate

python -m distyle_photo health
python -m distyle_photo scan --limit 10 --category 21
python -m distyle_photo run --dry-run --limit 10 --skip-on-sale --non-standard-only
python -m distyle_photo run --apply --limit 10 --skip-on-sale --non-standard-only --skip-processed
```

## Checklist

- [x] Projektas sukurtas lokaliai
- [ ] server venv + pip install
- [ ] client venv + pip install
- [ ] ollama pull moondream
- [ ] Langas 1: Ollama
- [ ] Langas 2: python main.py
- [ ] Langas 3: health → scan → dry-run

*Dokumentas: 2026-08-31*
