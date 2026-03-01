# matsposta

**CardPulse** — Sports card auction tracker using the eBay Finding and Trading APIs.

## Run with Python backend (recommended — keeps API keys off the frontend)

**Option A — one command (Mac/Linux):**
```bash
cd /Users/mathewsposta/matsposta
./run.sh
```

**Option B — step by step:**
```bash
cd /Users/mathewsposta/matsposta
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # then edit .env and add your eBay App ID and Cert ID
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Then open **http://127.0.0.1:8000**.

**If port 8000 is already in use:** stop the other app using it, or run on another port: `--port 8001` (then open http://127.0.0.1:8001).

## Quick start (static only)

1. Open **`card-tracker.html`** in a browser (double-click or run a local server).
2. To use live eBay data: add your [eBay Developer](https://developer.ebay.com/) App ID and Cert ID in the `CONFIG` object in the file (sandbox and/or production).

## Project layout

| File / folder       | Purpose |
|---------------------|--------|
| `app/main.py`       | FastAPI backend: `/api/listings`, eBay auth + Finding + Trading API. |
| `static/index.html` | Frontend when run via uvicorn (uses `API_BASE='/api'`). |
| `card-tracker.html` | Standalone frontend (for GitHub Pages or local open). Edit `CONFIG` for keys if not using backend. |
| `.env`              | eBay credentials (copy from `.env.example`). Not committed. |
| `cardpulse/`        | Ignored in git; optional nested project folder. |

## Env

- **Python backend:** set `EBAY_ENV=production` or `sandbox` in `.env`.
- **Static app:** use the ENV dropdown in the UI (SANDBOX / PRODUCTION).
