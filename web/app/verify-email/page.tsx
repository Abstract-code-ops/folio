import Link from "next/link";

export default function VerifyEmailPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-bg-base px-6 py-16">
      <div className="w-full max-w-sm text-center">
        <h1 className="font-heading text-h2 text-text-primary">Check your email</h1>
        <p className="mt-3 text-body text-text-muted">
          We&apos;ve sent a verification link to your email address. Open it to
          activate your account, then sign in.
        </p>
        <Link
          href="/sign-in"
          className="mt-6 inline-block rounded-md bg-accent px-4 py-2 text-body-sm font-medium text-white hover:opacity-90"
        >
          Back to sign in
        </Link>
      </div>
    </main>
  );
}
