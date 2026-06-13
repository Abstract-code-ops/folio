# UI Context

## Theme

Dark only. No light mode. The design language is a dark technical workspace
built for sustained reading sessions — near-black backgrounds, two distinct
surface levels that separate study tools from reading surface, and a warm
amber-to-green color ramp reserved exclusively for coverage state. Interactive
UI elements use a single cool accent that never competes with coverage color.

The PDF reader is the primary surface and always receives dominant space.
The left sidebar and right sidebar are secondary — present but subordinate.

-----

## Colors

All components use these CSS custom property tokens. No hardcoded hex values
anywhere in component code.

|Role                            |CSS Variable      |Value    |
|--------------------------------|------------------|---------|
|Page background                 |`--bg-base`       |`#0E0E0F`|
|Sidebar surface                 |`--bg-surface`    |`#161618`|
|Elevated surface (cards, panels)|`--bg-elevated`   |`#1E1E21`|
|Reader surface                  |`--bg-reader`     |`#131314`|
|Primary text                    |`--text-primary`  |`#F0EEE9`|
|Muted text                      |`--text-muted`    |`#6B6A6F`|
|Subtle text (captions, labels)  |`--text-subtle`   |`#4A4950`|
|Primary accent (interactive UI) |`--accent-primary`|`#6E56CF`|
|Accent hover                    |`--accent-hover`  |`#7C66D8`|
|Border default                  |`--border-default`|`#252528`|
|Border subtle                   |`--border-subtle` |`#1C1C1F`|
|Error                           |`--state-error`   |`#E05252`|
|Success                         |`--state-success` |`#4ADE80`|
|Warning                         |`--state-warning` |`#F59E0B`|

### Coverage Color Scale

These tokens are used exclusively for coverage state rendering on the
coverage map. They must not be used for any other UI purpose — the visual
meaning of amber-to-green must remain unambiguous.

|Coverage State    |Score|CSS Variable           |Value                           |
|------------------|-----|-----------------------|--------------------------------|
|Uncovered         |0    |`--coverage-none`      |`#252528` (border only, no fill)|
|Mentioned         |1–4  |`--coverage-low`       |`#92400E`                       |
|Partial           |5–9  |`--coverage-mid`       |`#D97706`                       |
|Well covered      |10–15|`--coverage-high`      |`#4ADE80`                       |
|Connective section|any  |`--coverage-connective`|`#1E1E21` (reduced weight)      |

The ramp deliberately moves from amber (warm, incomplete) to green (cool,
complete) to encode the sense of growth over time. Connective sections use
the elevated surface color with no coverage fill regardless of score.

-----

## Typography

Geist Sans throughout all surfaces including the reader. No serif or humanist
variant. The technical character of Geist is the intended personality.

|Role                |Font      |Variable     |Weight|Size       |
|--------------------|----------|-------------|------|-----------|
|UI text             |Geist Sans|`--font-sans`|400   |`0.875rem` |
|UI labels / captions|Geist Sans|`--font-sans`|400   |`0.75rem`  |
|UI medium emphasis  |Geist Sans|`--font-sans`|500   |`0.875rem` |
|Sidebar headings    |Geist Sans|`--font-sans`|600   |`0.75rem`  |
|Reader body         |Geist Sans|`--font-sans`|400   |`1rem`     |
|Mono / code         |Geist Mono|`--font-mono`|400   |`0.8125rem`|

Reader surface gets `line-height: 1.75` and `letter-spacing: 0.01em` to
create a reading environment distinct from the UI surfaces, without changing
the typeface.

-----

## Border Radius

|Context                        |Class       |Value     |
|-------------------------------|------------|----------|
|Inline elements, tags, badges  |`rounded`   |`0.25rem` |
|Buttons, inputs, small cards   |`rounded-md`|`0.375rem`|
|Sidebar panels, coverage blocks|`rounded-lg`|`0.5rem`  |
|Modals, overlays, library cards|`rounded-xl`|`0.75rem` |

Do not introduce radius values outside this scale.

-----

## Icons

Lucide React. Stroke-based only. No filled icon variants.

|Context                  |Size         |
|-------------------------|-------------|
|Inline / text-adjacent   |`h-3.5 w-3.5`|
|Sidebar tab icons        |`h-4 w-4`    |
|Button icons             |`h-4 w-4`    |
|Empty state illustrations|`h-8 w-8`    |

Stroke width: `1.5` throughout. Never `2` — it reads as too heavy against
the dark surface.

-----

## Layout

### Shell — Main Reader View

Three-zone layout. The reader always occupies the dominant space.

```
┌──────────────────────────────────────────────────────────┐
│  [icon rail] [left panel]  [   PDF READER   ]  [right]   │
│                                                           │
│  ◀ 48px ▶◀── 280px ────▶◀──── flex-1 ──────▶◀─ 240px ▶  │
│  (fixed)  (collapsible)         (min 600px)  (collapse)  │
└──────────────────────────────────────────────────────────┘
```

- **Icon rail** (left, fixed, 48px): vertical strip with tab icons for
  Coverage Map, Chat, Notes. Active tab highlighted with `--accent-primary`.
  Always visible — never collapses.
- **Left panel** (collapsible, 280px when open): expands from the icon rail.
  Contains the active tab content. Collapsed by default on viewports under
  1280px. Toggle is the active icon rail button.
- **PDF reader** (center, `flex-1`): always present, always primary.
  Background `--bg-reader`. Minimum width 600px — left panel collapses
  before the reader shrinks.
- **Right sidebar** (collapsible, 240px when open): account, settings,
  book info. Collapsed by default. Opened via a settings icon in the
  top-right corner. Uses `--bg-surface`.

Sidebar borders use `--border-subtle` — barely visible, not decorative.

### Shell — Library View (no book selected)

Full-screen library. The three-column shell is not rendered. Navigation is
minimal — just the Folio wordmark and a sign-in/account control top right.

```
┌──────────────────────────────────────────────────────────┐
│  Folio                                         [account] │
├──────────────────────────────────────────────────────────┤
│                                                           │
│   Your library        Open-access library                 │
│   ──────────────      ──────────────────                  │
│   [book card] ...     [book card] [book card] ...         │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

Book cards show: cover thumbnail (or generated placeholder), title, author,
section count, and ingestion status (ready / processing / not started).

### Left Panel — Tab Contents

**Coverage Map tab:**
Hierarchical block list. Chapter rows are full-width, section rows are
indented. Block height is proportional to the section’s word count — denser
sections are taller. Block fill color maps to coverage state via the
coverage color scale. Connective sections render at 60% opacity with no
fill. Hover shows a tooltip: heading, page range, word count, coverage score.
Click navigates the reader to that section’s first page.

**Chat tab (AI Q&A):**
Standard chat layout. User messages right-aligned, AI responses left-aligned.
Every AI response includes a source citation chip (section name + page range)
that links to that page in the reader. “Not covered in this section” responses
render in `--text-muted` to visually distinguish them from grounded answers.
Input is pinned to the bottom of the panel. Scope label above the input shows
which section the chat is currently scoped to.

**Notes tab (Lecture Notes / Note Sessions):**
List of submitted note sessions, most recent first. Each session shows
submission date, matched section count, and a expand/collapse toggle. Expanded
view shows the matched sections as coverage map mini-chips. A “New session”
button is pinned above the list. Clicking it opens a modal for paste/type
input or AI note generation.

-----

## Responsive Behavior

Folio is a responsive web app. The layout adapts across four breakpoints.
Mobile is fully supported but the experience is intentionally reader-first —
study tools are accessible via bottom navigation rather than sidebars.

### Breakpoints

|Name   |Width            |Tailwind prefix|
|-------|-----------------|---------------|
|Mobile |`< 640px`        |(default)      |
|Tablet |`640px – 1023px` |`sm:`          |
|Laptop |`1024px – 1279px`|`lg:`          |
|Desktop|`≥ 1280px`       |`xl:`          |

-----

### Desktop (`xl:` — ≥ 1280px)

Full three-zone layout as described in the Shell section above. Left panel
defaults open. Right sidebar defaults closed.

```
┌──────────────────────────────────────────────────────────┐
│  [rail][left panel 280px]  [  PDF READER flex-1  ][right]│
└──────────────────────────────────────────────────────────┘
```

-----

### Laptop (`lg:` — 1024px–1279px)

Left panel defaults **closed** to give the reader maximum space. Icon rail
still visible. Right sidebar hidden entirely — account/settings accessible
via a menu inside the icon rail instead.

```
┌──────────────────────────────────────────────────────────┐
│  [rail]  [       PDF READER — full remaining width      ] │
└──────────────────────────────────────────────────────────┘
```

Opening a left panel tab overlays 280px on top of the reader with a
semi-transparent backdrop — it does not push the reader. Clicking outside
the panel or pressing Escape closes it.

-----

### Tablet (`sm:` — 640px–1023px)

Icon rail collapses into a bottom navigation bar with three icon buttons
(Coverage, Chat, Notes) plus a settings icon. The reader fills the full
viewport width. Tapping a bottom nav icon opens the corresponding panel
as a bottom sheet that slides up to 65% of the viewport height. The reader
remains partially visible behind the sheet.

```
┌─────────────────────────────┐
│                             │
│      PDF READER             │
│      (full width)           │
│                             │
│─────────────────────────────│  ← bottom sheet when panel open
│  [Coverage panel content]   │
│─────────────────────────────│
│  [▦ Coverage][✦ Chat][≡ Notes][⚙] │  ← bottom nav bar
└─────────────────────────────┘
```

Bottom sheet dismisses by swiping down or tapping the reader area above it.

-----

### Mobile (default — < 640px)

Single-surface layout. Only one surface is visible at a time — reader,
coverage, chat, or notes. Bottom navigation switches between surfaces
with a full-height transition (slide left/right).

```
┌─────────────────┐
│                 │
│   PDF READER    │  ← active surface (or coverage / chat / notes)
│   (full height) │
│                 │
│─────────────────│
│ [▦][✦][≡]  [⚙] │  ← bottom nav, always visible
└─────────────────┘
```

The library view on mobile is a single-column card list. Book cards stack
vertically. Search/filter controls collapse into a single filter icon that
opens a bottom sheet.

PDF reader on mobile: page-by-page navigation with swipe left/right.
Pinch-to-zoom enabled. Page controls (prev/next, page number input) appear
as a floating bar at the bottom of the reader surface, above the nav bar.

Coverage map on mobile: block widths fill the full panel width. Word-count
proportional heights are preserved. Chapter labels are sticky as the user
scrolls.

-----

### Touch Targets

All interactive elements meet a minimum touch target of `44px × 44px` on
touch devices regardless of their visible size. Use padding to extend the
target without changing the visual footprint.

-----

### Hover States

Hover states (tooltips, coverage block hover detail) are desktop-only.
On touch devices, the same information surfaces on tap — a tap on a
coverage block opens a bottom sheet with section detail and a
“Open in reader” button rather than showing a tooltip.

-----

## Signature Element

**Word-count-proportional block sizing on the coverage map.**

Section blocks in the coverage map vary in height proportionally to the
section’s word count, within a defined range (`min-height: 24px`,
`max-height: 80px`). This makes the map a genuine visual representation of
the book’s content density — a long, dense chapter section is visibly
larger than a two-paragraph connective passage. Combined with the amber→green
fill, a well-studied book looks visually saturated and complete in a way
that feels earned. An unstudied book looks sparse and cool. This is the
primary visual payoff of the product.

Do not flatten block heights to a uniform size. The proportional sizing is
intentional and must be preserved in all coverage map implementations.

-----

## Motion

Minimal and purposeful. Two cases only:

- **Coverage fill transitions:** when a section’s coverage state upgrades
  (e.g. from mentioned to partial), animate the fill color change with a
  `300ms ease-out` transition. This is the only moment of ambient animation
  in the product — it signals that the map is alive and responding to study
  activity.
- **Panel open/close:** sidebar panels slide in/out with a `200ms ease-in-out`
  transition on `width` and `opacity`. No bounce, no spring.

All other UI state changes are instant. Respect `prefers-reduced-motion` —
both transitions above must be disabled when the user has reduced motion
enabled.

-----

## Component Library

shadcn/ui on top of Tailwind. Components live in `web/components/ui/`.
Add new components via the shadcn CLI only — never edit these files manually.

Feature-specific components live in:

- `web/components/coverage/` — coverage map, section blocks, coverage tooltips
- `web/components/reader/` — PDF viewer wrapper, page controls
- `web/components/notes/` — note session list, session detail, new session modal
- `web/components/chat/` — chat thread, message bubbles, source citation chips

-----

## Empty States

Every panel and tab must have a defined empty state. Empty states direct
the user toward an action — they are not decorative.

|Surface     |Empty condition                 |Message                                                          |Action                       |
|------------|--------------------------------|-----------------------------------------------------------------|-----------------------------|
|Coverage map|Book selected, ingestion running|“Building your coverage map…”                                    |Progress indicator, no action|
|Coverage map|No book selected                |“Select a book to see its coverage map.”                         |Link to library              |
|Chat        |No section open                 |“Open a section in the reader to ask a question about it.”       |No button                    |
|Notes       |No sessions submitted           |“Add a note session to start filling in your map.”               |“Add notes” button           |
|Library     |No books in personal library    |“Your library is empty. Browse open-access books to get started.”|“Browse books” button        |

Empty state messages use `--text-muted`. Icons use `h-8 w-8` at
`--text-subtle`. No illustrations beyond the icon.

-----

## Writing Conventions

- Sentence case everywhere. No title case in UI labels.
- Actions name what happens: “Add notes”, “Ask a question”, “Open in reader” —
  not “Submit”, “Send”, “Go”.
- Coverage states are named as the student experiences them: “Not started”,
  “Mentioned”, “Partial”, “Well covered” — not internal enum names.
- Error messages say what happened and what to do. Never “Something went wrong.”
  Instead: “Couldn’t load this section. Try refreshing.” or “Note session
  failed to submit. Check your connection and try again.”
- The AI panel is called “Chat” in the UI, not “AI Tutor” or “Q&A”.
  The coverage map is called “Coverage” in the tab label.
  Note sessions are called “Notes” in the tab label.