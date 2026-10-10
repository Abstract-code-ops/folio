import { readFileSync } from "fs";
import path from "path";

// Loads the founder's note from web/content/founder-note.md.
// The text before "—" is the note; after it is the signature name.
export function PersonalNote() {
  const raw = readFileSync(
    path.join(process.cwd(), "content", "founder-note.md"),
    "utf8",
  );
  const [body, signature] = raw.split("—");
  const paragraphs = body
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  const name = (signature ?? "").trim() || "Your name";

  return (
    <section id="about" className="bg-bg-surface">
      <div className="mx-auto max-w-[65ch] px-6 py-24">
        <p className="font-heading text-body-sm text-text-subtle">
          Why I built this
        </p>
        <div className="mt-6 space-y-5 border-t border-border pt-8">
          {paragraphs.map((p, i) => (
            <p
              key={i}
              className="font-body text-body-lg leading-relaxed text-text-primary"
            >
              {p}
            </p>
          ))}
        </div>
        <div className="mt-10 flex items-center gap-3">
          <div className="h-10 w-10 rounded-full border border-border bg-bg-elevated" />
          <span className="font-heading text-body-sm text-text-muted">
            {name}
          </span>
        </div>
      </div>
    </section>
  );
}
