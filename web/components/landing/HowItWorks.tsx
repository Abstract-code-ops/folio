import { landing } from "@/content/landing";

export function HowItWorks() {
  return (
    <section id="how-it-works" className="bg-bg-surface">
      <div className="mx-auto max-w-3xl px-6 py-24">
        <h2 className="font-body text-3xl font-semibold text-text-primary">
          {landing.howItWorks.title}
        </h2>
        <ol className="mt-10 space-y-8">
          {landing.howItWorks.steps.map((s, i) => (
            <li key={i} className="flex gap-6">
              <span className="font-body text-4xl text-text-subtle">
                {i + 1}
              </span>
              <div>
                <h3 className="font-heading text-body-lg text-text-primary">
                  {s.title}
                </h3>
                <p className="mt-1 font-body text-body text-text-muted">
                  {s.description}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
