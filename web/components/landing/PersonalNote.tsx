import { readFileSync } from "fs";
import path from "path";
import { NoteSection, type NoteData } from "./NoteSection";

type BeatMeta = { id: string; label: string; marginNote: string };
type Segment = { text: string; highlight: boolean };

function unquote(s: string): string {
  const t = s.trim();
  if ((t.startsWith('"') && t.endsWith('"')) || (t.startsWith("'") && t.endsWith("'"))) {
    return t.slice(1, -1);
  }
  return t;
}

function extractSection(body: string, id: string): string {
  const match = body.match(new RegExp(`## ${id}\\s*\\n`));
  if (!match) return "";
  const start = match.index! + match[0].length;
  const rest = body.slice(start);
  const next = rest.match(/\n## /);
  const end = next ? next.index! : rest.length;
  return rest.slice(0, end).trim();
}

function splitHighlights(text: string): Segment[] {
  return text
    .split("==")
    .map((t, i) => ({ text: t.trim(), highlight: i % 2 === 1 }))
    .filter((s) => s.text.length > 0);
}

function parseNote(raw: string): NoteData {
  const m = raw.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
  const fm = m?.[1] ?? "";
  const body = m?.[2] ?? raw;

  const data: Record<string, string> = {};
  const meta: BeatMeta[] = [];

  let current: BeatMeta | null = null;
  for (const line of fm.split("\n")) {
    const beat = line.match(/^\s*-\s+id:\s*(.+)$/);
    if (beat) {
      current = { id: beat[1].trim(), label: "", marginNote: "" };
      meta.push(current);
      continue;
    }
    const kv = line.match(/^(\w+):\s*(.*)$/);
    if (!kv) continue;
    const key = kv[1];
    const val = unquote(kv[2]);
    if (key === "beats") continue;
    if (current) (current as Record<string, string>)[key] = val;
    else data[key] = val;
  }

  const beats: NoteData["beats"] = meta.map((b) => ({
    id: b.id,
    label: b.label,
    marginNote: b.marginNote,
    segments: splitHighlights(extractSection(body, b.id)),
  }));

  return {
    name: data.name ?? "",
    photo: data.photo ?? "",
    signature: data.signature ?? "",
    beats,
  };
}

export function PersonalNote() {
  const raw = readFileSync(
    path.join(process.cwd(), "content", "founder-note.md"),
    "utf8",
  );
  const note = parseNote(raw);
  return <NoteSection {...note} />;
}
