# DiStyle Photo Pipeline — AGENTS.md

> Dokumentas AI agentams ir developeriams. Aprašo visą `distyle-photo-pipeline` programą nuo A iki Z.

## Kas tai?

Automatinis **sofų produktų nuotraukų standartizavimo pipeline** svetainei **distyle.lt** (WooCommerce).

**Tikslas:** peržiūrėti visą produkto galeriją, **sugeneruoti** naują priekinį studio kadrą (`#edece8`, 1920×1920 WebP) su paprastu natūraliu šešėliu — **nekarpyti** rembg/mask (karpymas gadina siūles ir šviesų audinį). Apply režime įkelti kaip naują pagrindinę nuotrauką.

**Nekeičia:** kainų, aprašymų, kategorijų — tik produkto `images` masyvą WooCommerce.

---

## Architektūra

```
┌─────────────────────────────────────────────────────────────┐
│  Langas 3: Python klientas (client/)                        │
│  python -m distyle_photo run                                │
│    ├── WooCommerce REST API (skaityti produktus)            │
│    ├── WordPress REST API (apply: upload media)             │
│    └── HTTP → Langas 2                                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Langas 2: AI serveris (server/) — FastAPI :8765            │
│    POST /vision/score  — heuristika + Ollama llava          │
│    POST /generate      — naujas studio kadras is reference   │
│    └── HTTP → Langas 1                                      │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│  Langas 1: Ollama — :11434                                  │
│  Modelis: llava (numatytasis; moondream neberekomenduojamas)│
└─────────────────────────────────────────────────────────────┘
```

---

## Projekto kelias

```
C:\Users\Alanas\Desktop\digroup\distyle WP\distyle-photo-pipeline\
├── client/                  # Pipeline CLI + WooCommerce integracija
│   ├── distyle_photo/       # Python paketas
│   ├── output/              # Sugeneruotos nuotraukos + CSV logai
│   ├── backups/             # JSON backup prieš apply + processed markeriai
│   └── .venv/
├── server/                  # FastAPI AI serveris
│   ├── main.py
│   ├── cutout.py
│   ├── image_heuristics.py
│   ├── vision_ollama.py
│   └── .venv/
├── .env                     # ⭐ PAGRINDINIS env (WC + WP + AI)
├── server/.env              # Serverio env (Ollama, API key)
├── setup_local_digroup.ps1
├── README.md
├── LOKALUS_SETUP_PILNAS.md
└── AGENTS.md                # Šis failas
```

**Pastaba:** yra ir `distyle WP/.env` (tėvinis katalogas), bet klientas **pirmiausia** krauna `distyle-photo-pipeline/.env`. Redaguok **tik pipeline `.env`**, ne tėvinį.

---

## Diegimas (vieną kartą)

```powershell
cd "C:\Users\Alanas\Desktop\digroup\distyle WP\distyle-photo-pipeline"
.\setup_local_digroup.ps1
ollama pull llava
```

---

## Paleidimas (3 langai)

### Langas 1 — Ollama
```powershell
ollama serve
```

### Langas 2 — AI serveris
```powershell
cd server
.venv\Scripts\activate
python main.py
# → http://127.0.0.1:8765/health
```

### Langas 3 — Pipeline
```powershell
cd client
.venv\Scripts\activate
python -m distyle_photo health
python -m distyle_photo scan --limit 10 --category 21
python -m distyle_photo run --limit 10 --category 21 --skip-on-sale --non-standard-only
```

**Po kodo pakeitimų `server/` — būtina perkrauti Langą 2.**

---

## Konfigūracija (.env)

### `distyle-photo-pipeline/.env` (klientas)

| Kintamasis | Aprašymas |
|---|---|
| `WC_URL` | `https://distyle.lt` |
| `WC_CONSUMER_KEY` | WooCommerce REST API raktas |
| `WC_CONSUMER_SECRET` | WooCommerce REST API secret |
| `WP_USER` | **WordPress vartotojo vardas** (pvz. `Alanas`) — NE Application Password pavadinimas |
| `WP_APP_PASSWORD` | Application Password (24 simboliai, be tarpų) |
| `AI_SERVER_URL` | `http://127.0.0.1:8765` |
| `AI_SERVER_API_KEY` | Turi sutapti su serverio `CUTOUT_API_KEY` |
| `VISION_SCORE_THRESHOLD` | Min. balas (default `70`) |
| `CATEGORY_ID` | WooCommerce kategorija (sofos = `21`) |
| `OUTPUT_DIR` | `./output` |
| `BACKUP_DIR` | `./backups` |
| `BG_COLOR_R/G/B` | Studijinis fonas (237/236/232 = `#edece8`) |

### `server/.env`

| Kintamasis | Aprašymas |
|---|---|
| `CUTOUT_API_KEY` | `local-test-key` (sutampa su klientu) |
| `OLLAMA_URL` | `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | `llava` |
| `PORT` | `8765` |

### WordPress Application Password

1. WP Admin → viršuje dešinėje **vartotojo vardas** → **Redaguoti profilį**
2. Slinkti žemyn → **Programų slaptažodžiai** (*Application Passwords*)
3. Add New → nukopijuoti raktą į `WP_APP_PASSWORD`
4. `WP_USER` = tikras WP login vardas (`Alanas`), **ne** programos pavadinimas (`photo-pipeline`)

**Dažna klaida:** `WP_USER=photo-pipeline` — tai programos label, ne vartotojas → 401 Unauthorized.

---

## CLI komandos

```powershell
python -m distyle_photo health          # WC + AI server + WP auth
python -m distyle_photo scan [opcijos]  # Kandidatų sąrašas (nieko nekeičia)
python -m distyle_photo run [opcijos]   # Dry-run (default) arba --apply
```

### `run` opcijos

| Opcija | Default | Aprašymas |
|---|---|---|
| `--apply` | off | Tikras upload į distyle.lt |
| `--limit N` | 10 | Kiek produktų apdoroti |
| `--category ID` | iš .env | WC kategorija |
| `--product-ids` | — | Konkretūs ID: `41672,41644` |
| `--skip-on-sale` | on | Praleisti produktus su nuolaida |
| `--non-standard-only` | on | Praleisti jau standartizuotus (Ditre Italia markeriai) |
| `--skip-processed` | off | Praleisti jau apply'intus (žr. backups/) |

### Tipinės komandos

```powershell
# RunPod: vienkartinis setup (Ubuntu GPU VM)
bash setup_runpod.sh

# Health (WC + AI server + WP auth)
python -m distyle_photo health

# ETAPAS 1 — 2 random sofos, tik output (be WP)
python -m distyle_photo preview-batch

# ETAPAS 2 — 10 random sofu + apply i distyle.lt (po tavo OK)
python -m distyle_photo test-batch

# ETAPAS 3 — visos sofos + apply (po test-batch OK)
python -m distyle_photo batch-all

# Vienas produktas
python -m distyle_photo run --product-ids 41590 --apply
```

**RunPod DI:** `server/.env` → `LOCAL_IMAGE_DEVICE=cuda`, `LOCAL_IMAGE_MODEL=black-forest-labs/FLUX.1-Kontext-dev`, `HF_TOKEN` (accept license HF). Ne API, ne Cursor.

**Tik sofos:** kategorija `21`, papildomas vardo filtras (ne pufas/fotelis).

---

## Pipeline eiga (run)

```
1. Gauti produktus (WC API, kategorija arba --product-ids)
2. Filtruoti (selectors.py):
   - skip on_sale
   - skip already_standardized (DitreItalia_Sofas URL markeriai)
   - skip gallery_too_small (< 2 nuotraukos)
3. Kiekvienam produktui — visada generate (ne crop):
   a. Visos nuotraukos (featured + galerija); praleisti armchair URL
   b. POST /vision/score — parinkti geriausias reference
   c. POST /generate — vienas universalus promptas (front-on, #edece8, minkštas contact shadow)
   d. Letterbox į 1920×1920 — be rembg / choke
4. Išsaugoti client/output/product_{ID}_studio.webp
5. Jei --apply:
   a. backup_images → backups/product_{ID}_images.json
   b. upload_media → WP REST API
   c. update_product_images (nauja nuotrauka = featured)
   d. mark_processed → backups/product_{ID}_processed.json
6. CSV log → client/output/run_{timestamp}.csv
```

---

## Nuotraukų parinkimo kriterijai

### Ko IEŠKOME (geras rezultatas)

- Viena sofa, **priekis į kamerą**, eye-level (ne 3/4)
- Švarus kadras, sofa **apatiniame viduryje**, užpildo plotį
- Studijinis `#edece8` fonas **sugeneruotas kartu su kadrų** (ne cutout)
- 1920×1920 WebP
- Vienas minkštas natūralus contact shadow ant grindų

### Ko ATMETAME

- **Overhead / top-down** — kamera iš viršaus
- **Side clutter** — lempa, staliukas, kėdė, pouf (heuristika baudžia; cutout bando pašalinti)
- **Portrait profile** — šoninis profilis
- **Flat overhead spread** — vienodas plotis visose juostose + aukštas centroid
- **Overhead uniform fill** — fill > 78% + mažas perspektyvos skirtumas
- Cutout validacija: `centroid_y < 0.58`, `overhead_layout`, `side_clutter`, `multiple_blobs`

### Scoring sluoksniai

1. **`image_heuristics.py`** — greita PIL analizė (perspektyva, fill, clutter, clusters). `reject=true` = hard reject.
2. **`vision_ollama.py`** — llava prompt, score 0–100. Koreguoja galutinį balą; reject tik jei score < 35.
3. **`cutout.py`** — rembg + blob cleanup + validacija. **Galutinis vartai** — jei `valid=false`, bando kitą galerijos nuotrauką.

---

## AI serverio API

Visi POST reikalauja header: `X-Api-Key: local-test-key`

### `GET /health`
```json
{"status":"ok","ollama":"ok","ollama_model":"llava","cutout":"ok"}
```

### `POST /vision/score`
- Input: multipart `file` (JPEG/PNG/WebP bytes)
- Output: `{score, heuristic_score, ollama_score, reject, heuristic_details, ollama_details}`

### `POST /cutout`
- Input: multipart `file`, optional `width`, `height`, `quality`, `meta=true`
- Output: WebP bytes arba JSON su `valid`, `meta`, `webp_b64`

---

## Išvesties failai

| Kelias | Turinys |
|---|---|
| `client/output/product_{ID}_studio.webp` | Studijinė nuotrauka |
| `client/output/run_{timestamp}.csv` | Run log (status, score, klaidos) |
| `client/backups/product_{ID}_images.json` | Originalių nuotraukų backup prieš apply |
| `client/backups/product_{ID}_processed.json` | Apply marker (--skip-processed) |

### Run statusai

| Statusas | Reikšmė |
|---|---|
| `dry_run` | Nuotrauka sugeneruota lokaliai |
| `applied` | Įkelta į distyle.lt |
| `no_suitable_image` | Nė viena galerijos nuotrauka nepraėjo filtrų |
| `error` | Klaida (dažniausiai 401 WP upload) |

---

## Svarbūs source failai

| Failas | Paskirtis |
|---|---|
| `client/distyle_photo/cli.py` | CLI entry point |
| `client/distyle_photo/pipeline.py` | Pagrindinis orchestratorius |
| `client/distyle_photo/woo.py` | WC + WP REST API |
| `client/distyle_photo/selectors.py` | Produktų filtrai |
| `client/distyle_photo/image_urls.py` | Galerijos URL iš WC objekto |
| `client/distyle_photo/vision.py` | AI serverio klientas (/vision/score) |
| `client/distyle_photo/cutout.py` | AI serverio klientas (/cutout) |
| `client/distyle_photo/config.py` | .env loading (3 keliai, pirmas laimi) |
| `server/main.py` | FastAPI routes |
| `server/image_heuristics.py` | Heuristinis scoring |
| `server/vision_ollama.py` | Ollama llava integracija |
| `server/cutout.py` | rembg, mask cleanup, studio canvas |

---

## Troubleshooting

### 401 Unauthorized (WP upload)
- `WP_USER` turi būti WP **vartotojo vardas**, ne Application Password pavadinimas
- `WP_APP_PASSWORD` = Application Password, ne login slaptažodis
- Raktas `.env` be tarpų
- Tikrinti: `python -m distyle_photo health` → `wp_upload.wp_auth: ok`

### AI server timeout
- llava užimtas (vienas request ~1–3 min) — health gali timeout'inti kol vyksta run
- Perkrauk serverį po `server/` kodo pakeitimų

### moondream tuščias atsakymas
- Naudoti `llava` (`server/.env`: `OLLAMA_MODEL=llava`)

### Visi produktai `no_suitable_image`
- Griežti filtrai — galerijoje nėra priekinio eye-level kadro
- Sprendimai: pridėti geresnes nuotraukas į WP, arba (atsargiai) atlaisvinti `image_heuristics.py` / `cutout.py` validaciją

### Per lėtas run
- llava ~1–3 min/nuotrauka × galerijos dydis × produktų skaičius
- 10 produktų gali trukti 30–90 min

### Jau standartizuoti praleidžiami
- `--non-standard-only` ieško `DitreItalia_Sofas` ir pan. URL markerių
- Naudoti `--all` jei reikia apdoroti visus

---

## Saugumas

- **Niekada necommitinti** `.env` su raktais
- Apply režimas keičia **gyvą** distyle.lt — visada dry-run pirma
- `backups/` saugo originalias nuotraukas prieš apply
- Nenaudoti `--apply` be `health` patikros

---

## Žinomos ribos (2026-09-01)

- Kategorija 21 (sofos): daug FLEXTEAM/LAGO produktų turi tik overhead kambario kadrus — pipeline teisingai praleidžia
- Paskutinis dry-run: **1/10** sėkmė (Hero 41590), 9× `no_suitable_image`
- Anksčiau su silpnesniais filtrais generavo 10/10, bet dalis buvo blogos perspektyvos (overhead, lempos)
- OpenAI / Supabase / VPS **nereikia** crop keliui (Ollama + rembg)
- **Generate** kelias: `GEMINI_API_KEY` arba `OPENAI_API_KEY` arba `HF_TOKEN` serverio `.env`

---

## Greita agento checklist

- [ ] Ollama veikia (`ollama serve`)
- [ ] AI serveris veikia (`GET :8765/health`, model=llava)
- [ ] `.env` teisingas (`distyle-photo-pipeline/.env`, WP_USER=Alanas)
- [ ] `python -m distyle_photo health` — visi ok
- [ ] Dry-run → peržiūrėti `client/output/*.webp`
- [ ] `--apply` tik po patvirtinimo

---

*Atnaujinta: 2026-09-01*
