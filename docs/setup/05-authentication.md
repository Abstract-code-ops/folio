# 5. Authentication setup

Folio uses [**Better Auth**](https://www.better-auth.com/) for sessions. The browser holds
an HttpOnly session cookie; the Next proxy resolves it to a Bearer token; FastAPI
validates the token against Better Auth's `session` table.

## Env
```dotenv
BETTER_AUTH_SECRET=<random 32+ bytes>
BETTER_AUTH_URL=https://<your-public-url>       # must match where the app is served
NEXT_PUBLIC_AUTH_ENABLED=true
AUTH_REQUIRED=true                               # fail-closed; app refuses to boot with auth off in production
```

## How it works
1. **Sign in** at `/sign-in` (email verification via `/verify-email`).
2. Browser → same-origin `/api/proxy/*`; the proxy calls `auth.api.getSession` and forwards
   the session `token` as `Authorization: Bearer …` (token never reaches browser JS).
3. FastAPI resolves it in `app/core/auth.py` (`get_current_user`, `require_admin`) with a
   30 s in-process token cache.

## Admin allow-list
Admin-only actions (create/delete books, trigger ingest, status) require the caller's
account **email** to be in the allow-list:
```dotenv
# app/core/config.py: admin_emails (comma-separated). Empty = nobody (fail-closed).
ADMIN_EMAILS=you@example.com
```
Set this to your account's email so `/admin` works.

![Sign-in page](./assets/05-sign-in.png)
<!-- CAPTURE: /sign-in page, and a screenshot of a signed-in /admin page. -->
GIF: sign-in → admin access
![Auth flow demo](./assets/05-auth-flow.gif)
<!-- GIF (8–12s): click Sign in → enter email → verify → land on /library → open /admin. -->

## Guest mode (unauthenticated trial)
Guests can **read** and use a limited trial **without an account**:
- **10 Q&A turns + 3 notes**, stored **client-side only** (never in the DB).
- Backend `get_optional_user` lets Q&A stream anonymously with **no DB writes**; IP
  rate-limited. Note *generation* is disabled for guests (prompts sign-in instead).
- On sign-in, the guest's local data is discarded and the account's data (or empty) loads.

## Roles summary
| Role | Can do |
|------|--------|
| Guest | browse catalog, read, 10 Q&A + 3 local notes |
| User | everything + persistent notes/chat |
| Admin (allow-listed email) | + `/admin` ingest, add/delete books, categories |

## Next
→ [6. Deployment](./06-deployment.md)
