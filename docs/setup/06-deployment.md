# 6. Deployment

## Services
| Service | Command | Port |
|---------|---------|------|
| `api` | `uvicorn main:app --host 0.0.0.0 --port 8000` | 8000 |
| `web` | `next start` (after `next build`) | 3000 |

The reference container runs the web dev-server (`sleep infinity` + manual `npm run build` /
`next start`); see `docs/dev-scripts.md` for the full run/rebuild flow.

## ⚠️ Two build gotchas
1. **`NODE_ENV=production`** — build in production mode (the dev `NODE_ENV=development` in
   compose causes prerender warnings/failures).
2. **`NEXT_PUBLIC_API_URL` must be `/api/proxy`** — it's inlined at build. If the host
   globally sets `NEXT_PUBLIC_API_URL=http://api:8000` (a Docker-internal host), the browser
   can't reach it. Unset it before building:

```bash
# from the host
env -u NEXT_PUBLIC_API_URL npm --prefix web run build

# or inside the container
docker exec -e NODE_ENV=production -e NEXT_PUBLIC_API_URL=/api/proxy folio-web-1 npm run build
```

![Production build success](./assets/06-build.png)
<!-- CAPTURE: terminal — `next build` ending with the route table / "Compiled successfully". -->

## Deploy sequence
```bash
# 1. schema
docker exec folio-api-1 python3 -m alembic upgrade head      # → 0011

# 2. install web deps (if changed) + build
docker exec folio-web-1 npm install
docker exec -e NODE_ENV=production -e NEXT_PUBLIC_API_URL=/api/proxy folio-web-1 npm run build

# 3. (re)start servers — you own this step
#    web: kill old next start; start `npx next start`
#    api: uvicorn (auto-reloads in dev)

# 4. PDF worker asset (after fresh compose up)
cp web/public/pdf.worker.min.mjs web/public/pdf.worker.min.js
docker cp web/public/pdf.worker.min.js folio-web-1:/workspace/web/public/pdf.worker.min.js
```

## Health checks
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/        # 200
curl -s http://localhost:8000/books                                    # 200 JSON
docker exec folio-api-1 python3 -m alembic current                     # 0011
```

GIF: deploy → live
![Deploy demo](./assets/06-deploy.gif)
<!-- GIF (12–20s): build → start → curl health checks → open the site. -->

## Observability (optional)
```dotenv
NEXT_PUBLIC_SENTRY_DSN=      # browser errors
SENTRY_DSN=                  # web server + API errors
NEXT_PUBLIC_POSTHOG_KEY=     # product analytics
NEXT_PUBLIC_POSTHOG_HOST=https://eu.i.posthog.com
```
Sentry initializes in `web/instrumentation*.ts` + `api/main.py`; PostHog in
`web/components/analytics/PostHogProvider.tsx`.

## Public exposure (optional)
For phone/remote access, the reference setup uses an ngrok tunnel:
```bash
docker exec folio-web-1 ngrok http 3000 --log=stdout
```
Set `NEXT_PUBLIC_API_URL=/api/proxy` stays same-origin (no CORS). If you proxy the API
through ngrok directly, add the `ngrok-skip-browser-warning` header (already added on
admin calls).

## Next
→ [7. Adding books](./07-adding-books.md)
