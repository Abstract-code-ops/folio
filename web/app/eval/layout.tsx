// Server-side gate for the /eval route: only emails listed in
// EVAL_ALLOWED_EMAILS (comma-separated) may view it. Everyone else is redirected
// to the library. This is the page gate; the underlying /qa/turns endpoint stays
// per-user, so a blocked user cannot read anyone else's turns either.

import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { auth } from "@/lib/auth";

const ALLOWED_EMAILS = (process.env.EVAL_ALLOWED_EMAILS ?? "")
  .split(",")
  .map((email) => email.trim().toLowerCase())
  .filter(Boolean);

export default async function EvalLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth.api.getSession({ headers: await headers() });
  const email = session?.user?.email?.toLowerCase() ?? "";

  if (!email || !ALLOWED_EMAILS.includes(email)) {
    redirect("/library");
  }

  return <>{children}</>;
}
