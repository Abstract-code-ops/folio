import Link from "next/link";
import { BarChart3, Upload, ArrowRight } from "lucide-react";

const LINKS = [
  {
    href: "/ingest",
    title: "Ingest books",
    description:
      "Add a book and run the ingestion pipeline. Watch live progress — sections and chunks as they are written.",
    icon: Upload,
  },
  {
    href: "/eval",
    title: "Q&A eval",
    description:
      "Every question, what the agent retrieved, and what came back — with retrieval distances.",
    icon: BarChart3,
  },
];

export default function AdminPage() {
  return (
    <div className="min-h-dvh bg-bg-base">
      <header className="sticky top-0 z-10 border-b border-border-subtle bg-bg-surface px-4 py-3">
        <div className="mx-auto flex w-full max-w-4xl items-center gap-3">
          <Link
            href="/library"
            className="text-body-sm text-text-muted transition-colors hover:text-text-primary"
          >
            ← Library
          </Link>
          <h1 className="font-heading text-body font-semibold text-text-primary">
            Admin
          </h1>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl px-4 py-8">
        <p className="mb-6 text-body text-text-muted">
          Curator tools for this Folio instance.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          {LINKS.map(({ href, title, description, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="group flex flex-col gap-3 rounded-xl border border-border-subtle bg-bg-surface p-5 transition-colors hover:border-accent/40 hover:bg-bg-elevated"
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/10 text-accent">
                <Icon className="h-5 w-5" strokeWidth={1.75} />
              </span>
              <span className="flex items-center gap-1.5 font-heading text-body font-semibold text-text-primary">
                {title}
                <ArrowRight className="h-4 w-4 text-text-subtle transition-transform group-hover:translate-x-0.5" />
              </span>
              <span className="text-body-sm text-text-muted">{description}</span>
              <span className="mt-1 font-mono text-body-sm text-text-subtle">
                {href}
              </span>
            </Link>
          ))}
        </div>
      </main>
    </div>
  );
}
