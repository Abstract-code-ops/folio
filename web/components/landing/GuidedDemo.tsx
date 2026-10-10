import { demo } from "@/content/landing-demo";

// Static, non-functional demo mock (scripted in a later phase).
export function GuidedDemo() {
  return (
    <section className="mx-auto max-w-5xl px-6 py-24">
      <div className="grid gap-10 lg:grid-cols-[1fr_1.4fr] lg:gap-16">
        {/* Captions */}
        <ol className="space-y-8">
          {demo.steps.map((s, i) => (
            <li key={i} className="flex gap-4">
              <span className="font-body text-2xl text-accent">{i + 1}</span>
              <span className="font-heading text-body-lg text-text-primary">
                {s.caption}
              </span>
            </li>
          ))}
        </ol>

        {/* App window mock */}
        <div className="overflow-hidden rounded-xl border border-border bg-bg-surface">
          <div className="flex items-center justify-between border-b border-border px-4 py-2">
            <span className="font-heading text-body-sm text-text-muted">
              A resource
            </span>
            <span className="font-heading text-body-sm text-text-subtle">
              p. 1
            </span>
          </div>

          {/* Reader skeleton */}
          <div className="flex flex-col gap-3 p-6">
            {[10, 8, 9, 7, 9, 6].map((w, i) => (
              <div
                key={i}
                className="h-2.5 rounded-sm bg-bg-elevated"
                style={{ width: `${w * 8}%` }}
              />
            ))}
          </div>

          {/* Chat mock */}
          <div className="border-t border-border p-4">
            <div className="mb-3 flex justify-end">
              <div className="rounded-lg bg-accent/15 px-3 py-2 font-body text-body-sm text-text-primary">
                {demo.question}
              </div>
            </div>
            <div className="flex justify-start">
              <div className="max-w-[85%] rounded-lg bg-bg-elevated px-3 py-2 font-body text-body-sm text-text-primary">
                {demo.answer}
                <span className="mt-2 flex items-center gap-2 rounded-md bg-bg-base px-2 py-1 font-heading text-body-sm text-text-subtle">
                  p. {demo.citationPage}
                </span>
              </div>
            </div>
            <div className="mt-3 rounded-lg border border-border px-3 py-2 font-heading text-body-sm text-text-subtle">
              Ask a question…
            </div>
          </div>
        </div>
      </div>
      <p className="mt-4 text-center font-heading text-body-sm text-text-subtle">
        Illustrative demo
      </p>
    </section>
  );
}
