import { landing } from "@/content/landing";

export function Topics() {
  return (
    <section id="topics" className="mx-auto max-w-3xl px-6 py-24">
      <h2 className="font-body text-3xl font-semibold text-text-primary">
        {landing.topics.title}
      </h2>
      <p className="mt-2 font-body text-body text-text-muted">
        {landing.topics.subtitle}
      </p>
      <ul className="mt-10">
        {landing.topics.items.map((t) => (
          <li
            key={t.name}
            className="group border-t border-border py-4 last:border-b"
          >
            <div className="flex items-baseline justify-between">
              <span className="font-heading text-body-lg text-text-primary group-hover:underline">
                {t.name}
              </span>
              <span className="font-heading text-body-sm text-text-subtle">
                {t.count} {t.count === 1 ? "pick" : "picks"}
              </span>
            </div>
            <p className="mt-1 font-body text-body text-text-muted">{t.blurb}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
