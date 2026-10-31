// Better Auth configuration.
//
// Better Auth runs inside Next.js and owns the `user` / `session` / `account`
// tables. Those tables live *outside* Alembic (see docs/architecture.md) — this
// is the one sanctioned place where the web app talks to Postgres directly, and
// it is confined to the auth schema. FastAPI only ever *reads* the `session`
// table (api/app/core/auth.py).
//
// Column names are mapped to snake_case so they line up with what the API
// queries: `token` (the session token), `user_id`, `expires_at`.
//
// Security posture (see the approved plan):
//   - email + password, with email verification required before we trust the
//     address;
//   - rate limiting on the auth endpoints;
//   - HttpOnly + SameSite cookies (Secure in production);
//   - generic errors (Better Auth does not reveal whether an account exists).

import { betterAuth } from "better-auth";
import { Pool } from "pg";
import { sendEmail, verificationEmail } from "./email";

const connectionString =
  process.env.DATABASE_URL ?? process.env.DATABASE_URL_ASYNC;

// Supabase (and most hosted Postgres) requires TLS, but node-postgres does not
// enable SSL from a bare connection string the way psycopg2 does. Turn SSL on
// for remote/hosted URLs and don't hard-fail on the provider cert chain in dev
// (pin a CA before production if you want strict verification).
const useSsl = !!connectionString && /supabase|sslmode=/.test(connectionString);
const pool = new Pool({
  connectionString,
  ...(useSsl ? { ssl: { rejectUnauthorized: false } } : {}),
});

// App origin used to build auth URLs (verification links, callbacks). Override
// with NEXT_PUBLIC_APP_URL. BETTER_AUTH_URL is misconfigured in this env (it
// holds the Supabase *database* host), so ignore it; the dev default is the
// ngrok tunnel the app is served on.
const configuredUrl =
  process.env.NEXT_PUBLIC_APP_URL ?? process.env.BETTER_AUTH_URL ?? "";
const appBaseUrl =
  configuredUrl && !configuredUrl.includes("supabase.co")
    ? configuredUrl
    : "https://doze-computer-dragging.ngrok-free.dev";

// Trusted origins: configurable via BETTER_AUTH_TRUSTED_ORIGINS
// (comma-separated) plus these dev defaults. A missing origin is the
// INVALID_ORIGIN 403, so every host the app is opened from must be listed.
const DEFAULT_TRUSTED_ORIGINS = [
  "http://localhost:3000",
  "http://localhost:3001",
  "http://127.0.0.1:3000",
  "https://doze-computer-dragging.ngrok-free.dev",
];
const trustedOrigins = [
  ...DEFAULT_TRUSTED_ORIGINS,
  ...(process.env.BETTER_AUTH_TRUSTED_ORIGINS ?? "")
    .split(",")
    .map((origin) => origin.trim())
    .filter(Boolean),
];
if (!trustedOrigins.includes(appBaseUrl)) trustedOrigins.push(appBaseUrl);

export const auth = betterAuth({
  // A pg Pool is a supported database adapter for Postgres. Better Auth creates
  // and manages its own tables in this database.
  database: pool,

  secret: process.env.BETTER_AUTH_SECRET,
  baseURL: appBaseUrl,
  trustedOrigins,

  emailAndPassword: {
    enabled: true,
    requireEmailVerification: true,
    sendResetPassword: async ({ user, url }: { user: { email: string }; url: string }) => {
      await sendEmail({
        to: user.email,
        subject: "Reset your Folio password",
        text: `Reset your password:\n\n${url}`,
        html: `<p><a href="${url}">Reset your password</a></p>`,
      });
    },
  },

  // Email verification is required before the address is trusted. There is no
  // mail transport wired yet, so verification links are logged to the server
  // console in development. TODO(email transport): swap in a real provider
  // (Resend/SMTP) before production — the console sender must not ship.
  emailVerification: {
    sendOnSignUp: true,
    sendVerificationEmail: async ({ user, url }: { user: { email: string }; url: string }) => {
      await sendEmail({ to: user.email, ...verificationEmail(url) });
    },
  },

  // snake_case mapping so the `session` table matches api/app/core/auth.py.
  session: {
    modelName: "session",
    // Remember the user for 30 days; refresh the expiry once a day.
    expiresIn: 60 * 60 * 24 * 30,
    updateAge: 60 * 60 * 24,
    fields: {
      userId: "user_id",
      expiresAt: "expires_at",
      createdAt: "created_at",
      updatedAt: "updated_at",
      ipAddress: "ip_address",
      userAgent: "user_agent",
    },
  },
  user: {
    fields: {
      emailVerified: "email_verified",
      createdAt: "created_at",
      updatedAt: "updated_at",
    },
  },
  account: {
    fields: {
      userId: "user_id",
      accountId: "account_id",
      providerId: "provider_id",
      accessToken: "access_token",
      refreshToken: "refresh_token",
      accessTokenExpiresAt: "access_token_expires_at",
      refreshTokenExpiresAt: "refresh_token_expires_at",
      createdAt: "created_at",
      updatedAt: "updated_at",
    },
  },

  // Cookie hygiene: HttpOnly + SameSite=Lax; Secure is applied automatically in
  // production (over HTTPS). Forcing it on in dev drops the cookie on
  // http://localhost.
  advanced: {
    useSecureCookies: process.env.NODE_ENV === "production",
    defaultCookieAttributes: {
      httpOnly: true,
      sameSite: "lax",
    },
    database: {
      // Better Auth defaults to nanoid string ids. The FastAPI side stores user
      // ids in UUID columns and parses them with uuid.UUID(), so generate UUIDs
      // for new rows. (Users created before this change keep their nanoid id
      // and must be re-created.)
      generateId: () => crypto.randomUUID(),
    },
  },

  // Throttle sign-in / sign-up / password-reset attempts.
  rateLimit: {
    enabled: true,
  },
});
