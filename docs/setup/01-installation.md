# 1. Installation requirements

## Prerequisites
| Requirement | Version | Notes |
|-------------|---------|-------|
| Docker Engine | 24+ | |
| Docker Compose | v2 (`docker compose`, not `docker-compose`) | |
| RAM | ≥ 4 GB free | Ollama (embeddings) + API + Next |
| Disk | ≥ 5 GB | Images + models + PDFs |
| Free ports | `3000` (web), `8000` (api), `11434` (Ollama) | |

Node 20 and Python 3.12 are **provided inside the images** — you don't install them on the host.

## Steps
```bash
git clone <repo> ~/folio && cd ~/folio

# 1. Create .env (see required variables below)
cp .env.example .env   # or create .env by hand
$EDITOR .env

# 2. Build + start
docker compose up -d

# 3. Verify
docker ps | grep folio          # folio-web-1 and folio-api-1 "Up"
curl http://localhost:8000/books   # 200 []
```

![Installation: containers up](./assets/01-installation-containers.png)
<!-- CAPTURE: terminal — `docker compose up -d` then `docker ps | grep folio`; both containers "Up". -->

## Required `.env` variables
```dotenv
# Database (Supabase Postgres)
DATABASE_URL=postgresql://USER:PASS@HOST:5432/postgres
DATABASE_URL_ASYNC=postgresql+asyncpg://USER:PASS@HOST:5432/postgres

# Supabase Storage
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>

# Auth
BETTER_AUTH_SECRET=<random-32-bytes>
BETTER_AUTH_URL=https://<project>.supabase.co
AUTH_REQUIRED=true
NEXT_PUBLIC_AUTH_ENABLED=true
EVAL_ALLOWED_EMAILS=you@example.com

# AI providers
GEMINI_API_KEY=<key>
VOID_API_KEY=<key>
# VOID_API_BASE / VOID_MODEL have sane defaults

# Frontend
NEXT_PUBLIC_API_URL=/api/proxy

# Observability (optional)
NEXT_PUBLIC_SENTRY_DSN=
SENTRY_DSN=
NEXT_PUBLIC_POSTHOG_KEY=
NEXT_PUBLIC_POSTHOG_HOST=https://eu.i.posthog.com
```

GIF: end-to-end first boot
![Installation demo](./assets/01-installation-boot.gif)
<!-- GIF (10–15s): `docker compose up -d` → wait → open http://localhost:3000 → library shell renders. -->

## Next
→ [2. Database configuration](./02-database.md)
