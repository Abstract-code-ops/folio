# Setup docs — media assets

The setup guides reference screenshots and short GIFs from this folder. They are
**placeholders** until captured: each guide has a `![…](./assets/<name>.png|gif)` line plus a
`<!-- CAPTURE … -->` / `<!-- GIF … -->` comment describing exactly what to record.

## Naming convention
| File | Shows | Type |
|------|-------|------|
| `00-architecture.png` | `docker compose ps` or an architecture sketch | image |
| `01-installation-containers.png` | containers `Up` after `docker compose up -d` | image |
| `01-installation-boot.gif` | first boot → library renders | gif |
| `02-supabase-pooler.png` | Supabase pooler / pool sizing | image |
| `02-migrations.gif` | `alembic upgrade head` → `current` = 0011 | gif |
| `03-pgvector-extension.png` | `vector` extension present | image |
| `03-vector-ingest.gif` | ingest → vectors + kind counts | gif |
| `04-ollama.png` | `ollama list` (nomic-embed-text) | image |
| `04-figure-captioning.gif` | ingest → "Captioned N figure(s)" | gif |
| `05-sign-in.png` | `/sign-in` + signed-in `/admin` | image |
| `05-auth-flow.gif` | sign in → land on library/admin | gif |
| `06-build.png` | `next build` success | image |
| `06-deploy.gif` | build → start → health checks | gif |
| `07-add-book-form.png` | Add-a-book form filled | image |
| `07-add-and-ingest.gif` | add → start ingestion → Ready | gif |

## How to capture
- **Screenshots**: OS screenshot tool; keep width ≤ 1400 px; crop to the relevant UI.
- **GIFs**: 5–20 s; keep under ~5 MB. Suggested: [LICEcap], [Peek] (Linux), [Kap] (mac), or
  `ffmpeg`/`gifski` from a screen recording. Trim dead time; a terminal + browser is enough.
- Reference with relative paths from the doc: `![alt](./assets/07-add-and-ingest.gif)`.

> Tip: many of these overlap — one good "add → ingest → Ready" GIF can satisfy both
> `07-add-and-ingest.gif` and the vector demo.
