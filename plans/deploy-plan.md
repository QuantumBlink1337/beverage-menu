# GOON Beverage Site — Deployment Plan

Status: **planning**. MVP is feature-complete; this covers containerizing and deploying it.

## Goal
Containerize the FastAPI app and deploy it to the **Nucleus** server, fronted by a reverse
proxy for HTTPS + a domain. Original plan called for Tailscale Serve; we're now favoring
**Nginx Proxy Manager (NPM)** for public guest access (QR codes), with Tailscale optional for
private/admin access.

## App runtime facts (from the repo)
- **Python 3.12**, FastAPI + uvicorn. Deps pinned in `requirements.txt` (note: it also includes
  dev deps `pytest`, `pytest-asyncio` — candidates to trim from the prod image).
- **Entrypoint:** `uvicorn main:app` run **from the `app/` directory** — the code uses flat
  imports (`from db import ...`, `from models import ...`) that assume cwd = `app/`.
- Serves **static files** (`app/static`) at URL root `/`; API under `/api/*`.
- **SQLite DB** at `DB_PATH` (default `beverage.db`, relative to cwd). Holds the Grocy/Notion
  caches + ingredient mappings → **must persist** across restarts (volume).
- **Env vars** (secrets; currently in gitignored `.env`):
  `GROCY_URL`, `GROCY_API_KEY`, `NOTION_API_KEY`, `NOTION_CRAFTED_DRINKS_DB_ID`, `DB_PATH` (optional).
- **Startup (`lifespan` in `app/main.py`):** initializes the DB and, if the recipe cache is
  stale, **refreshes from Notion at boot** → the container needs network + valid Notion creds
  when it starts. The first `/api/beverages` request refreshes the Grocy cache.
- **Grocy client uses `verify=False`** (self-signed Tailscale cert). Reachability of Grocy from
  Nucleus must be confirmed (LAN HTTP vs Tailscale HTTPS) — and whether `verify=False` is still
  appropriate there.

## Dockerization (draft)
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./                      # main.py/db.py land at /app (matches flat imports); static at /app/static
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```
- `.dockerignore`: `.git`, `.venv`, `tests/`, `plans/`, `__pycache__`, `*.pyc`, `.env`,
  `app/beverage.db`, `.ruff_cache`, `.pytest_cache`.
- Optional: a slimmer prod requirements without pytest.

## Persistence & secrets
- **DB volume:** set `DB_PATH=/data/beverage.db` and mount a named volume at `/data`.
- **Secrets:** `env_file: .env` on the server (or compose `environment:` / Docker secrets) —
  never baked into the image. `.env` stays gitignored.

## docker-compose (draft)
```yaml
services:
  beverage-menu:
    build: .
    restart: unless-stopped
    env_file: .env
    environment:
      DB_PATH: /data/beverage.db
    volumes:
      - beverage-db:/data
    networks: [proxy]            # shared with NPM; no published host port needed
volumes:
  beverage-db:
networks:
  proxy:
    external: true
```

## Reverse proxy — Nginx Proxy Manager (preferred)
- Put the app container and NPM on a shared Docker network (`proxy`, external).
- NPM **Proxy Host**: `drinks.<domain>` → `http://beverage-menu:8000`, request a Let's Encrypt
  cert. No need to publish 8000 on the host if NPM reaches it over the Docker network.
- **Tailscale (original plan):** still useful for private host-mode (`?host=true`) access, or as
  a fallback. Could run both — NPM public + Tailscale private.

## Deployment runbook (draft)
1. Get code onto Nucleus (git clone, or build image in CI + push to a registry).
2. Create `.env` on the server with the four secrets (+ `DB_PATH`).
3. Ensure the external `proxy` network exists (shared with NPM).
4. `docker compose up -d --build`.
5. NPM: add the proxy host + SSL cert; point DNS at the server.
6. Warm caches (hit `/api/beverages` + `/api/crafted_drinks`) so the first guest load is fast.
7. Smoke test: `/`, `/?host=true`, tab switching, expand a cocktail.

## Open questions (resolve with Matt)
- **What is "Nucleus"?** A Docker host? Same box as Grocy/Unraid, or separate? OS?
- **Public access:** is there a domain + DNS pointing at it? Let's Encrypt via NPM
  (HTTP-01 needs port 80 reachable, or use a DNS-01 challenge)?
- **Grocy reachability** from Nucleus: LAN HTTP or Tailscale HTTPS? Does `verify=False` still
  apply, or can we use a real cert / plain HTTP on the LAN?
- **Code delivery:** build on the server from git, or build an image and push to a registry?
- **Keep Tailscale** for private host-mode access alongside NPM?

## Pre-deploy data checklist (carried from the build)
- Reassign Grocy products into the new granular groups (Beer/Wine/Bourbon/…); refresh the grocy cache.
- Create the `THCMixer` Grocy group (THC spirit) — see `GROUP_TABS` in `app/static/app.js`.
- Add a `Featured` tag in Notion + tag highlight cocktails; set Notion tag colors.
- Refresh the recipe cache so cocktails repopulate with the new `{name,color}` tag shape.
