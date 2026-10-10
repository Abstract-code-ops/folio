import Link from "next/link";
import { landing } from "@/content/landing";
import { Shelf } from "./Shelf";

export function Hero() {
  return (
    <header className="relative overflow-hidden">
      <div className="mx-auto max-w-5xl px-6">
        <nav className="flex items-center justify-between py-5">
          <span className="font-heading text-body font-semibold text-text-primary">
            Folio
          </span>
          <div className="flex items-center gap-6">
            <a
              href="#topics"
              className="font-heading text-body-sm text-text-muted hover:text-text-primary transition-colors"
            >
              {landing.nav.topics}
            </a>
            <a
              href="#how-it-works"
              className="font-heading text-body-sm text-text-muted hover:text-text-primary transition-colors"
            >
              {landing.nav.howItWorks}
            </a>
            <a
              href="#about"
              className="font-heading text-body-sm text-text-muted hover:text-text-primary transition-colors"
            >
              {landing.nav.about}
            </a>
            <span className="font-heading text-body-sm text-text-muted">
              {landing.nav.signIn}
            </span>
          </div>
        </nav>

        {/* Headline block stays above; shelf sits below with 32px of space */}
        <div className="flex flex-col items-center py-14 text-center md:py-20">
          <h1 className="max-w-2xl font-body text-4xl font-semibold leading-tight text-text-primary md:text-5xl">
            {landing.hero.headline}
          </h1>
          <p className="mt-5 max-w-prose font-body text-body-lg text-text-muted">
            {landing.hero.subheadline}
          </p>
          <div className="mt-8 flex items-center gap-6">
            <Link
              href="/library"
              className="rounded-md bg-accent px-5 py-2.5 font-heading text-body-sm text-white hover:bg-accent-hover transition-colors"
            >
              {landing.hero.primaryCta}
            </Link>
            <a
              href="#about"
              className="font-heading text-body-sm text-text-muted hover:text-text-primary transition-colors"
            >
              {landing.hero.secondaryCta} →
            </a>
          </div>
        </div>
      </div>

      {/* Full-width shelf — bleeds off both edges on mobile, clipped by the
          header's overflow-hidden; capped to the content column on desktop */}
      <div className="mx-auto mt-8 max-w-5xl pb-16 md:pb-24">
        <Shelf />
      </div>
    </header>
  );
}
