# 6. Deployment

## Services
| Service | Command | Port |
|---------|---------|------|
| `api` | `uvicorn main:app --host 0.0.0.0 --port 8000` | 8000 |
| `web` | `next start` (after `next build`) | 3000 |

The reference container runs the web dev-server (`sleep infinity` + manual `npm run build` /
`next start`); see `docs/dev-scripts.md` for the full run/rebuild flow.

**`NODE_ENV=production`** — build in production mode (the dev `NODE_ENV=development` in
   compose causes prerender warnings/failures).

```bash
# from the host
npm --prefix web run build

# or inside the container
docker exec -e NODE_ENV=production folio-web-1 npm run build
```

![Production build success](./assets/06-build.png)
<!-- CAPTURE: terminal — `next build` ending with the route table / "Compiled successfully". -->

## Deploy sequence
```bash
# 1. schema
docker exec folio-api-1 python3 -m alembic upgrade head      # → 0011

# 2. install web deps (if changed) + build
docker exec folio-web-1 npm install
docker exec -e NODE_ENV=production folio-web-1 npm run build

# 3. (re)start servers — you own this step
#    web: kill old next start; start `npx next start`
#    api: uvicorn (auto-reloads in dev)

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

## Next
→ [7. Adding books](./07-adding-books.md)
