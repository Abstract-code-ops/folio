import Link from "next/link";
import { landing } from "@/content/landing";

export function Footer() {
  return (
    <footer className="mx-auto max-w-3xl px-6 py-24 text-center">
      <p className="mx-auto max-w-prose font-body text-body-lg text-text-primary">
        {landing.closing.sentence}
      </p>
      <Link
        href="/library"
        className="mt-8 inline-block rounded-md bg-accent px-5 py-2.5 font-heading text-body-sm text-white hover:bg-accent-hover transition-colors"
      >
        {landing.closing.cta}
      </Link>
      <div className="mt-16 flex items-center justify-between border-t border-border pt-6">
        <span className="font-heading text-body-sm text-text-primary">Folio</span>
        <div className="flex gap-6">
          <a
            href="#about"
            className="font-heading text-body-sm text-text-subtle hover:text-text-primary transition-colors"
          >
            About
          </a>
          <a
            href="#how-it-works"
            className="font-heading text-body-sm text-text-subtle hover:text-text-primary transition-colors"
          >
            How it works
          </a>
        </div>
      </div>
    </footer>
  );
}
