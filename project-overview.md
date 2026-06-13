# Folio

## Overview

Folio is a book-first study platform that bridges the gap between sparse lecture
notes and the full depth of a textbook. Students select an open-access textbook,
and a coverage map is generated immediately from the book’s own structure — every
chapter and section laid out as a navigable map. As students add note sessions over
time, the map fills in, showing which sections their notes cover and at what depth.
An AI tutor grounded exclusively in the book helps them explore uncovered sections —
but always as a guide back to reading, never a replacement for it. Built for
university students and self-learners across any subject.

## Goals

1. Give students a single, persistent map of their textbook that fills in as they
   study — so they always know where they are and what they have missed
1. Encourage reading the source material first — the AI supports comprehension,
   it does not replace reading
1. Provide AI-generated lecture notes grounded in book structure, traceable to
   specific sections and pages

## Core User Flow

1. User signs in
1. User selects a textbook from the open-access library
1. A coverage map generates immediately from the book’s parsed structure — every
   chapter and section visible, all neutral (no coverage yet)
1. User adds a note session — pastes or types lecture notes, or requests
   AI-generated notes for a selected chapter range
1. The two-stage matching pipeline runs and relevant sections light up on the
   map with a coverage score of 0–3
1. User repeats step 4 over time — multiple note sessions accumulate into the
   same map; sections upgrade as coverage deepens
1. User clicks an uncovered or partially covered section on the map — the PDF
   reader opens to that section
1. After reading, the user can ask the AI a question about what they just read —
   answered only from that section, with source citations
1. Every AI answer includes a go-to-source link back to the relevant page in
   the reader

## Features

### Textbook Library

- Open-access textbook selection from a pre-loaded library
- Immediate structural parsing on selection: TOC extraction, chapter and section
  hierarchy, key term identification per section, connective section flagging
- No user account required to browse the library

### Coverage Map

- Whole-book map generated from book structure alone — no notes required to
  see the map
- Four visual states per section: uncovered (neutral), mentioned (light),
  partial (medium), well covered (full color) — driven by a 0–3 quality score
- Connective sections (short transitional passages) rendered with reduced
  visual weight — distinguished from genuine content gaps
- Map accumulates coverage across multiple note sessions — one map per book,
  updated progressively
- Section hover: shows heading, page range, key terms, word count
- Section click: opens the PDF reader to that page — the primary action,
  not the AI

### Note Sessions

- Paste or type external lecture notes to trigger coverage matching
- Request AI-generated notes for any selected chapter or section range
- AI-generated notes follow a fixed schema: concept name, one-sentence
  definition, plain-language explanation, one example from the text, one
  self-check question
- Generated notes are traceable to their source section and page
- Multiple sessions contribute to the same coverage map — session detail
  visible per section on hover

### Grounded AI Tutor

- Question input scoped to the currently open section — not the whole book
- Every answer cites the specific section and page it draws from
- Go-to-source button on every cited passage — opens the reader to that page
- “Explain simpler” and “go deeper” follow-up variants
- AI responds with “not covered in this section” rather than drawing on
  general knowledge — grounding is enforced, not optional
- Soft nudge before answering: if the student has not opened the section,
  prompt them to read it first

### Auth and Persistence

- Email and OAuth sign-in
- Persisted per user: selected books, coverage map state, note sessions,
  Q&A history

## Scope

### In Scope

- Open-access textbook library (pre-loaded)
- Structural PDF parsing: TOC extraction, section hierarchy, key term
  extraction, connective section detection
- Hierarchy-aware chunking with pedagogical coherence (definitions stay
  with their examples, chunks never cross section boundaries)
- Two-pass lecture note generation: structural extraction pass (no LLM),
  then grounded LLM generation pass
- Two-stage coverage matching: similarity threshold pass, then LLM
  quality scoring pass (0–3)
- Whole-book coverage map with progressive accumulation across note sessions
- Grounded Q&A scoped to the current section, with source citations and
  go-to-source navigation
- User auth and full session persistence
- Reading-first UI: book reader is the primary surface, AI panel is secondary
  and collapsible

### Out of Scope

- Teacher course builder and course sharing
- Knowledge graph and concept relationship mapping
- Multi-book or supplementary source support within a single session
- Adaptive difficulty inference — student manually toggles simplify or deeper
- Mobile-native app — responsive web only
- User-uploaded books of any kind in v1

## Success Criteria

1. Coverage map correctly identifies covered vs. uncovered sections with
   greater than 80% precision against a manually annotated ground truth
   on at least two test textbooks
1. Every AI answer cites a specific section and page, with a working
   go-to-source link that opens the reader to the correct location
1. A student can go from textbook selection to a populated coverage map
   in under three minutes after submitting their first note session
1. In usability testing, at least four out of five students describe the
   coverage map as immediately useful without explanation from the tester
1. The AI panel is visibly secondary to the book reader in the default
   layout — confirmed by at least four out of five usability testers
   interacting with the reader before the AI