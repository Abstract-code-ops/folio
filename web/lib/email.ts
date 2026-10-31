// Transactional email transport.
//
// Server-only (imported from web/lib/auth.ts). Uses Resend's HTTP API via fetch
// so there is no extra dependency to install. When RESEND_API_KEY is unset the
// message is logged instead of sent — that keeps the dev flow usable (the
// verification link shows in the console) without a provider.
//
// Env:
//   RESEND_API_KEY  - Resend API key (https://resend.com)
//   EMAIL_FROM      - From address, e.g. "Folio <noreply@yourdomain.com>".
//                     Must be a domain verified in Resend (their onboarding@resend.dev
//                     sandbox sender works for testing your own inbox).

type EmailPayload = {
  to: string;
  subject: string;
  text: string;
  html?: string;
};

const FROM = process.env.EMAIL_FROM ?? "Folio <onboarding@resend.dev>";

export async function sendEmail({ to, subject, text, html }: EmailPayload): Promise<void> {
  const apiKey = process.env.RESEND_API_KEY;

  if (!apiKey) {
    console.info(`[email:dev] to=${to} subject=${subject}\n${text}`);
    return;
  }

  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: FROM,
        to,
        subject,
        text,
        ...(html ? { html } : {}),
      }),
    });

    if (!res.ok) {
      console.error(`[email] Resend send failed (${res.status}): ${await res.text()}`);
    }
  } catch (err) {
    console.error("[email] Resend send threw:", err);
  }
}

/** The verification email body, shared by the auth callbacks. */
export function verificationEmail(url: string): Pick<EmailPayload, "subject" | "text" | "html"> {
  return {
    subject: "Verify your Folio email",
    text: `Confirm your email address to finish signing in:\n\n${url}\n\nIf you didn't request this, ignore this email.`,
    html: `<p>Confirm your email address to finish signing in:</p><p><a href="${url}">${url}</a></p><p>If you didn't request this, ignore this email.</p>`,
  };
}
