---
id: BR-009
title: "A title: with a colon"
status: open
severity: medium
area: ledger
found: 2026-09-02
source:
fixed_in:
related: [BR-001]
---

- **Found:** 2026-09-02
- **Where:** `src/entries.py`, the reader

A value holding `: ` reads as a nested mapping to a real YAML reader.

**Suggested fix:** quote it.

**What this evidence does not establish:** whether a hand-written entry ever carried one bare.
