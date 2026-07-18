# Dev Scripts — How to Start Everything

## Overview

Three processes need to be running:

| Process | Container | Port | Purpose |
|---------|-----------|------|---------|
| API server | `folio-api-1` | `8000` | FastAPI backend |
| Next.js (production) | `folio-web-1` | `3000` | Frontend via `next start` |
| ngrok tunnel | `folio-web-1` | → public URL | Exposes the frontend |

---

## 1. Start the containers

```bash
docker compose up -d
docker ps | grep folio
```

Expected:
```
folio-web-1   0.0.0.0:3000->3000/tcp
folio-api-1   0.0.0.0:8000->8000/tcp
```

---

## 2. API server

Verify:

```bash
curl http://localhost:8000/books
```

Restart after code changes:

```bash
docker restart folio-api-1
```

---

## 3. Build the frontend

⚠️ **Critical:** The host has `NEXT_PUBLIC_API_URL=http://api:8000` set globally.
This is a Docker-internal hostname the browser can't reach. You **must unset it
before every build** so the fallback `/api/proxy` (same-origin) is used.

**From the host** (`~/folio`):

```bash
env -u NEXT_PUBLIC_API_URL npm --prefix web run build
```

**From inside the container** (`docker exec -it folio-web-1 sh` → `/workspace/web`):

```bash
env -u NEXT_PUBLIC_API_URL npm run build
```

Verify the proxy URL was baked in:

```bash
grep -o "/api/proxy\|http://api:8000" .next/static/chunks/app/page-*.js | head -3
# Should show: /api/proxy
```

---

## 4. Start the Next.js production server

Kill old server, then start:

```bash
docker exec folio-web-1 sh -c 'kill $(lsof -ti :3000) 2>/dev/null; sleep 1'
docker exec folio-web-1 npx next start
```

Verify:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/
# 200
```

---

## 5. Start ngrok tunnel

**First time only** — install ngrok in the container:

```bash
docker exec folio-web-1 wget -q https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz -O /tmp/ngrok.tgz
docker exec folio-web-1 tar -xzf /tmp/ngrok.tgz -C /usr/local/bin/
docker exec folio-web-1 sh -c 'mkdir -p /root/.config/ngrok && echo "version: \"3\"
agent:
    authtoken: 3GBRj203I8tYSHns8WaCFZVbFAA_7H3TPteBqeYmY7QYQqYW3" > /root/.config/ngrok/ngrok.yml'
```

**Every time** — start the tunnel:

```bash
docker exec folio-web-1 ngrok http 3000 --log=stdout
```

Look for: `url=https://xxxx.ngrok-free.dev`

Stop the tunnel:

```bash
docker exec folio-web-1 kill $(lsof -ti :4040) 2>/dev/null
```

---

## 6. Sync code + rebuild

Copy updated files to the container:

```bash
docker cp web/app/page.tsx folio-web-1:/workspace/web/app/page.tsx
docker cp web/lib/api-client.ts folio-web-1:/workspace/web/lib/api-client.ts
```

After copying, rebuild from **inside** the container:

```bash
docker exec -it folio-web-1 sh
# inside:
cd /workspace/web
env -u NEXT_PUBLIC_API_URL npm run build
kill $(lsof -ti :3000) 2>/dev/null
npx next start
```

Or build on the host and copy the `.next` directory:

```bash
env -u NEXT_PUBLIC_API_URL npm --prefix web run build
docker exec folio-web-1 rm -rf /workspace/web/.next
docker cp web/.next folio-web-1:/workspace/web/.next
docker exec folio-web-1 sh -c 'kill $(lsof -ti :3000) 2>/dev/null; sleep 1'
docker exec folio-web-1 npx next start
```

---

## 7. PDF worker — keep in sync

After a fresh `docker compose up -d`, the worker file in the container must match:

```bash
cp web/public/pdf.worker.min.mjs web/public/pdf.worker.min.js
docker cp web/public/pdf.worker.min.js folio-web-1:/workspace/web/public/pdf.worker.min.js
```

Verify it's not 0 bytes:

```bash
docker exec folio-web-1 ls -la /workspace/web/public/pdf.worker.min.js
```

---

## 8. Quick start — everything at once

```bash
# 1. Containers
docker compose up -d

# 2. Build (must unset API_URL!)
env -u NEXT_PUBLIC_API_URL npm --prefix web run build

# 3. Copy build to container
docker exec folio-web-1 rm -rf /workspace/web/.next
docker cp web/.next folio-web-1:/workspace/web/.next

# 4. Kill old + start fresh
docker exec folio-web-1 sh -c 'kill $(lsof -ti :3000) 2>/dev/null; sleep 1'
docker exec folio-web-1 npx next start

# 5. Start ngrok
docker exec folio-web-1 ngrok http 3000 --log=stdout
```

---

## Troubleshooting

### "Couldn't load your library"

1. Check the proxy: `curl https://YOUR_NGROK_URL/api/proxy/books`
2. Check the API: `curl http://localhost:8000/books`
3. Check what URL is baked in:
   ```bash
   docker exec folio-web-1 sh -c 'grep -o "/api/proxy\|http://api:8000" /workspace/web/.next/static/chunks/app/page-*.js'
   ```
   If it shows `http://api:8000`, rebuild with `env -u NEXT_PUBLIC_API_URL npm run build`

### PDF "Load failed" or blank

1. Check worker size:
   ```bash
   docker exec folio-web-1 ls -la /workspace/web/public/pdf.worker.min.js
   ```
   If 0 bytes, re-copy (section 7).
2. Check PDF proxy:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" "https://YOUR_NGROK_URL/api/pdf?url=PASTE_STORAGE_URL_HERE"
   ```

### Port 3000 in use

```bash
sudo lsof -i :3000
sudo kill <PID>
```
